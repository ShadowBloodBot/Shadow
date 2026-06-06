import discord
from discord.ext import commands
from discord import SlashCommandGroup, Option
import os
import json
import asyncio
import httpx
from bs4 import BeautifulSoup
from urllib.parse import urlencode, quote_plus
import logging

# ==============================================================================
# CONSTANTS & CONFIGURATION
# ==============================================================================
ADMIN_ID = 482463400929263627
EMBED_COLOR = 0x2B0B35
PERSIST_DIR = os.getenv("PERSIST_PATH", "/data")
DATA_FILE = os.path.join(PERSIST_DIR, "realestate.json")

SCRAPER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Cache-Control": "max-age=0"
}

# ==============================================================================
# PERSISTENCE HELPERS
# ==============================================================================
def load_data() -> dict:
    if not os.path.exists(DATA_FILE):
        return {"target_thread_id": None, "saved_searches": {}}
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logging.error(f"[RealEstate] Error loading data: {e}")
        return {"target_thread_id": None, "saved_searches": {}}

def save_data(data: dict):
    os.makedirs(PERSIST_DIR, exist_ok=True)
    temp_file = f"{DATA_FILE}.tmp"
    try:
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
        os.replace(temp_file, DATA_FILE)
    except Exception as e:
        logging.error(f"[RealEstate] Error saving data atomically: {e}")

# ==============================================================================
# AUTOCOMPLETE HELPERS
# ==============================================================================
async def saved_search_autocomplete(ctx: discord.AutocompleteContext):
    data = load_data()
    searches = list(data.get("saved_searches", {}).keys())
    return [s for s in searches if ctx.value.lower() in s.lower()][:25]

# ==============================================================================
# COG IMPLEMENTATION
# ==============================================================================
class RealEstate(commands.Cog):
    def __init__(self, bot: discord.Bot):
        self.bot = bot
        self.data = load_data()
        self.client = httpx.AsyncClient(timeout=15.0, follow_redirects=True)
        logging.info("[RealEstate] Cog initialized. AsyncClient created.")

    def cog_unload(self):
        logging.info("[RealEstate] Cog unloading. Closing AsyncClient.")
        self.bot.loop.create_task(self.client.aclose())

    # --------------------------------------------------------------------------
    # CORE SCRAPER LOGIC
    # --------------------------------------------------------------------------
    # URL Structure for realestate.com.au:
    # Base path: /{intent}/in-{location}/list-{page}
    #   - intent: 'buy', 'rent', or 'sold'
    #   - location: space-replaced-with-plus URL-encoded string (e.g. 'bondi+beach')
    # Query parameters (translated from standard inputs):
    #   - minPrice / maxPrice: integer limits
    #   - numBeds / numBaths / numParkingSpaces: integer minimums
    #   - propertyType: string enum (house, apartment, townhouse, land)
    # This structure is standard and maps to their internal routing system.
    # --------------------------------------------------------------------------
    def build_url(self, filters: dict, page: int) -> str:
        intent = filters.get("listing_type", "buy").lower()
        
        location = filters.get("location", "")
        if location:
            loc_slug = quote_plus(location.replace(" ", "+"))
            base_path = f"https://www.realestate.com.au/{intent}/in-{loc_slug}/list-{page}"
        else:
            base_path = f"https://www.realestate.com.au/{intent}/list-{page}"

        params = {}
        if filters.get("min_price"): params["minPrice"] = filters.get("min_price")
        if filters.get("max_price"): params["maxPrice"] = filters.get("max_price")
        if filters.get("min_beds"): params["numBeds"] = filters.get("min_beds")
        if filters.get("min_baths"): params["numBaths"] = filters.get("min_baths")
        
        ptype = filters.get("property_type", "").lower()
        if ptype and ptype != "any":
            params["propertyType"] = ptype
            
        params["activeSort"] = "relevance"

        query_string = urlencode(params)
        full_url = f"{base_path}?{query_string}"
        return full_url

    def parse_html(self, html: str) -> list[dict]:
        soup = BeautifulSoup(html, 'html.parser')
        listings = []
        
        cards = soup.find_all('article')
        if not cards:
            cards = soup.find_all('div', {'data-testid': 'listing-card'})

        for card in cards:
            try:
                # Address & URL
                address_tag = card.find(['h2', 'a'], class_=lambda c: c and 'address' in c.lower())
                if not address_tag:
                    address_tag = card.find('a', href=lambda h: h and '/property-' in h)
                
                if not address_tag:
                    continue

                address = address_tag.get_text(strip=True)
                url_path = address_tag.get('href', '')
                listing_url = f"https://www.realestate.com.au{url_path}" if url_path.startswith('/') else url_path

                # Price
                price_tag = card.find(class_=lambda c: c and 'price' in c.lower())
                price = price_tag.get_text(strip=True) if price_tag else "Price on Application"

                # Features
                features = {"beds": "-", "baths": "-", "parking": "-"}
                feature_containers = card.find_all(class_=lambda c: c and 'feature' in c.lower())
                
                for container in feature_containers:
                    text = container.get_text(strip=True).lower()
                    if 'bed' in text or '🛏' in text: features['beds'] = text.replace('bed', '').replace('🛏', '').strip()
                    if 'bath' in text or '🚿' in text: features['baths'] = text.replace('bath', '').replace('🚿', '').strip()
                    if 'car' in text or '🚗' in text: features['parking'] = text.replace('car', '').replace('🚗', '').strip()

                if features['beds'] == "-":
                    for feature in card.find_all(attrs={"aria-label": True}):
                        label = feature["aria-label"].lower()
                        if 'bedroom' in label: features['beds'] = label.split()[0]
                        elif 'bathroom' in label: features['baths'] = label.split()[0]
                        elif 'parking' in label or 'car' in label: features['parking'] = label.split()[0]

                # Image
                img_tag = card.find('img')
                img_url = ""
                if img_tag:
                    img_url = img_tag.get('src') or img_tag.get('data-src') or ""

                # Property Type & Land Size
                ptype_tag = card.find(class_=lambda c: c and 'property-type' in c.lower())
                property_type = ptype_tag.get_text(strip=True) if ptype_tag else "Property"
                
                land_size_tag = card.find(class_=lambda c: c and 'land-size' in c.lower())
                land_size = f" • {land_size_tag.get_text(strip=True)}" if land_size_tag else ""

                listings.append({
                    "address": address,
                    "price": price,
                    "beds": features['beds'],
                    "baths": features['baths'],
                    "parking": features['parking'],
                    "type": f"{property_type}{land_size}",
                    "url": listing_url,
                    "image": img_url
                })
            except Exception as e:
                logging.warning(f"[RealEstate] Error parsing a property card: {e}")
                continue

        return listings

    async def execute_scrape(self, filters: dict, max_results: int) -> tuple[list[dict], str]:
        all_listings = []
        pages_to_scrape = 3
        status_message = "Success"

        for page in range(1, pages_to_scrape + 1):
            url = self.build_url(filters, page)
            logging.info(f"[RealEstate] Scraping page {page}: {url}")
            
            try:
                response = await self.client.get(url, headers=SCRAPER_HEADERS)
                if response.status_code == 403 or response.status_code == 429:
                    status_message = f"Site actively blocked the scraper (HTTP {response.status_code} Cloudflare/Anti-bot). Try again later."
                    break
                elif response.status_code != 200:
                    status_message = f"Failed to retrieve data (HTTP {response.status_code})."
                    break
                
                page_listings = await self.bot.loop.run_in_executor(None, self.parse_html, response.text)
                
                if not page_listings:
                    break
                    
                for listing in page_listings:
                    if listing['url'] not in [l['url'] for l in all_listings]:
                        all_listings.append(listing)
                        
                if len(all_listings) >= max_results:
                    break
                    
                await asyncio.sleep(1.5)

            except httpx.RequestError as e:
                logging.error(f"[RealEstate] Network error during scrape: {e}")
                status_message = f"Network error occurred: {e}"
                break
            except Exception as e:
                logging.error(f"[RealEstate] Unexpected error during scrape: {e}")
                status_message = f"Unexpected error occurred: {e}"
                break

        return all_listings[:max_results], status_message

    # --------------------------------------------------------------------------
    # COMMANDS
    # --------------------------------------------------------------------------
    @discord.slash_command(name="find_property", description="Scrape realestate.com.au for property listings")
    async def find_property(
        self,
        ctx: discord.ApplicationContext,
        location: Option(str, "Suburb, postcode, or region", required=False, default=""),
        listing_type: Option(str, "Buy, Rent, or Sold", choices=["Buy", "Rent", "Sold"], required=False, default="Buy"),
        min_price: Option(int, "Minimum price/rent", required=False, default=None),
        max_price: Option(int, "Maximum price/rent", required=False, default=None),
        min_beds: Option(int, "Minimum bedrooms", min_value=1, required=False, default=None),
        min_baths: Option(int, "Minimum bathrooms", min_value=1, required=False, default=None),
        property_type: Option(str, "Property type", choices=["House", "Apartment", "Townhouse", "Land", "Any"], required=False, default="Any"),
        max_results: Option(int, "Cap results (default 10, max 25)", min_value=1, max_value=25, required=False, default=10)
    ):
        await ctx.defer()
        
        filters = {
            "location": location,
            "listing_type": listing_type,
            "min_price": min_price,
            "max_price": max_price,
            "min_beds": min_beds,
            "min_baths": min_baths,
            "property_type": property_type
        }

        listings, status = await self.execute_scrape(filters, max_results)

        target_channel = ctx.channel
        thread_id = self.data.get("target_thread_id")
        if thread_id:
            try:
                thread = await self.bot.fetch_channel(thread_id)
                if thread:
                    target_channel = thread
            except Exception as e:
                logging.warning(f"[RealEstate] Could not resolve configured thread {thread_id}: {e}")

        if not listings:
            embed = discord.Embed(
                title="No Properties Found",
                description=f"**Status:** {status}\nNo results for the given filters. Try broadening your search.",
                color=EMBED_COLOR
            )
            embed.add_field(name="Location", value=location or "Any", inline=True)
            embed.add_field(name="Type", value=listing_type, inline=True)
            embed.add_field(name="Property", value=property_type, inline=True)
            if target_channel == ctx.channel:
                await ctx.respond(embed=embed)
            else:
                await target_channel.send(embed=embed)
                await ctx.respond(f"Results sent to <#{target_channel.id}>.", ephemeral=True)
            return

        summary = f"Found {len(listings)} results."
        if len(listings) == max_results:
            summary = f"Showing {max_results} results — refine your filters to see more specific matches."

        await ctx.respond(f"**Real Estate Scrape Complete:** {summary}")

        for listing in listings:
            embed = discord.Embed(
                title=listing["address"],
                description=f"**{listing['price']}**\n\n🛏️ {listing['beds']}   |   🚿 {listing['baths']}   |   🚗 {listing['parking']}",
                url=listing["url"],
                color=EMBED_COLOR
            )
            if listing["image"] and listing["image"].startswith("http"):
                embed.set_thumbnail(url=listing["image"])
            
            embed.set_footer(text=listing["type"])

            view = discord.ui.View()
            view.add_item(discord.ui.Button(label="View Listing", url=listing["url"], style=discord.ButtonStyle.link))

            try:
                await target_channel.send(embed=embed, view=view)
            except discord.HTTPException as e:
                logging.error(f"[RealEstate] Discord HTTP Error sending embed: {e}")
            
            await asyncio.sleep(0.5)

    @discord.slash_command(name="realestate_config", description="[Admin] Set the default output thread/channel ID")
    async def realestate_config(
        self, 
        ctx: discord.ApplicationContext, 
        thread_id: Option(str, "Thread or Channel ID (leave blank to clear)", required=False, default=None)
    ):
        if ctx.author.id != ADMIN_ID:
            await ctx.respond("Unauthorized. Only the core architect can use this command.", ephemeral=True)
            return

        if thread_id:
            try:
                parsed_id = int(thread_id)
                self.data["target_thread_id"] = parsed_id
                save_data(self.data)
                await ctx.respond(f"Target thread set to `<#{parsed_id}>`.", ephemeral=True)
            except ValueError:
                await ctx.respond("Invalid ID format. Must be an integer.", ephemeral=True)
        else:
            self.data["target_thread_id"] = None
            save_data(self.data)
            await ctx.respond("Target thread cleared. Output will default to the invocation channel.", ephemeral=True)

    @discord.slash_command(name="save_search", description="Save your current filter set for future use")
    async def save_search(
        self,
        ctx: discord.ApplicationContext,
        name: Option(str, "Name for this saved search", required=True),
        location: Option(str, "Suburb, postcode, or region", required=False, default=""),
        listing_type: Option(str, "Buy, Rent, or Sold", choices=["Buy", "Rent", "Sold"], required=False, default="Buy"),
        min_price: Option(int, "Minimum price/rent", required=False, default=None),
        max_price: Option(int, "Maximum price/rent", required=False, default=None),
        min_beds: Option(int, "Minimum bedrooms", min_value=1, required=False, default=None),
        min_baths: Option(int, "Minimum bathrooms", min_value=1, required=False, default=None),
        property_type: Option(str, "Property type", choices=["House", "Apartment", "Townhouse", "Land", "Any"], required=False, default="Any")
    ):
        filters = {
            "location": location,
            "listing_type": listing_type,
            "min_price": min_price,
            "max_price": max_price,
            "min_beds": min_beds,
            "min_baths": min_baths,
            "property_type": property_type
        }
        
        self.data.setdefault("saved_searches", {})[name] = filters
        save_data(self.data)
        
        await ctx.respond(f"Saved search `{name}` successfully.", ephemeral=True)

    @discord.slash_command(name="run_saved_search", description="Run a previously saved search")
    async def run_saved_search(
        self,
        ctx: discord.ApplicationContext,
        name: Option(str, "Name of the saved search", autocomplete=saved_search_autocomplete, required=True),
        max_results: Option(int, "Cap results (default 10, max 25)", min_value=1, max_value=25, required=False, default=10)
    ):
        filters = self.data.get("saved_searches", {}).get(name)
        if not filters:
            await ctx.respond(f"Saved search `{name}` not found.", ephemeral=True)
            return

        # Delegate execution back to the primary logic
        await self.find_property(
            ctx=ctx,
            location=filters.get("location"),
            listing_type=filters.get("listing_type"),
            min_price=filters.get("min_price"),
            max_price=filters.get("max_price"),
            min_beds=filters.get("min_beds"),
            min_baths=filters.get("min_baths"),
            property_type=filters.get("property_type"),
            max_results=max_results
        )

    @discord.slash_command(name="list_searches", description="List all saved searches and their parameters")
    async def list_searches(self, ctx: discord.ApplicationContext):
        searches = self.data.get("saved_searches", {})
        if not searches:
            await ctx.respond("No saved searches found.", ephemeral=True)
            return

        embed = discord.Embed(title="Saved Real Estate Searches", color=EMBED_COLOR)
        for name, filters in searches.items():
            desc = f"**Location:** {filters.get('location', 'Any')} | **Intent:** {filters.get('listing_type')}\n"
            desc += f"**Price:** {filters.get('min_price', '0')} - {filters.get('max_price', 'Any')}\n"
            desc += f"**Type:** {filters.get('property_type', 'Any')} | 🛏️ {filters.get('min_beds', 'Any')} | 🚿 {filters.get('min_baths', 'Any')}"
            embed.add_field(name=name, value=desc, inline=False)

        await ctx.respond(embed=embed, ephemeral=True)

    @discord.slash_command(name="delete_search", description="Delete a saved search")
    async def delete_search(
        self,
        ctx: discord.ApplicationContext,
        name: Option(str, "Name of the saved search to delete", autocomplete=saved_search_autocomplete, required=True)
    ):
        if name in self.data.get("saved_searches", {}):
            del self.data["saved_searches"][name]
            save_data(self.data)
            await ctx.respond(f"Deleted saved search `{name}`.", ephemeral=True)
        else:
            await ctx.respond(f"Saved search `{name}` not found.", ephemeral=True)

def setup(bot: discord.Bot):
    bot.add_cog(RealEstate(bot))
