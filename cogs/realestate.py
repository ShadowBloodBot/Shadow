# cogs/realestate.py
import discord
from discord.ext import commands
from discord import Option
import os
import json
import asyncio
import random
import logging
from bs4 import BeautifulSoup
from urllib.parse import urlencode, quote_plus
from curl_cffi.requests import AsyncSession

# ==============================================================================
# CONSTANTS
# ==============================================================================
ADMIN_ID     = 482463400929263627
EMBED_COLOR  = 0x2B0B35
PERSIST_DIR  = os.getenv("PERSIST_PATH", "/data")
DATA_FILE    = os.path.join(PERSIST_DIR, "realestate.json")

# Realistic Chrome headers — curl_cffi handles TLS fingerprinting,
# these headers cover the HTTP layer
SCRAPER_HEADERS = {
    "User-Agent":                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept":                    "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language":           "en-AU,en;q=0.9",
    "Accept-Encoding":           "gzip, deflate, br",
    "Connection":                "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest":            "document",
    "Sec-Fetch-Mode":            "navigate",
    "Sec-Fetch-Site":            "none",
    "Sec-Fetch-User":            "?1",
    "Cache-Control":             "max-age=0",
}

# ==============================================================================
# PERSISTENCE
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
        logging.error(f"[RealEstate] Error saving data: {e}")

# ==============================================================================
# AUTOCOMPLETE
# ==============================================================================
async def saved_search_autocomplete(ctx: discord.AutocompleteContext):
    data    = load_data()
    searches = list(data.get("saved_searches", {}).keys())
    return [s for s in searches if ctx.value.lower() in s.lower()][:25]

# ==============================================================================
# COG
# ==============================================================================
class RealEstate(commands.Cog):
    def __init__(self, bot: discord.Bot):
        self.bot  = bot
        self.data = load_data()
        # FIX: curl_cffi impersonates Chrome's TLS fingerprint (JA3/JA4).
        # httpx/requests use Python's TLS stack which Cloudflare detects and blocks.
        # chrome120 impersonation generates the correct ClientHello handshake.
        self.session = AsyncSession(impersonate="chrome120")
        logging.info("[RealEstate] Cog initialized with curl_cffi Chrome impersonation.")

    def cog_unload(self):
        asyncio.create_task(self.session.close())

    # --------------------------------------------------------------------------
    # URL BUILDER
    # URL structure for realestate.com.au:
    #   Base: https://www.realestate.com.au/{intent}/in-{location}/list-{page}
    #   intent: buy | rent | sold
    #   location: URL-encoded suburb/postcode (spaces → hyphens, e.g. "bondi-beach")
    #   Query params: minPrice, maxPrice, numBeds, numBaths, propertyType, activeSort
    # --------------------------------------------------------------------------
    def build_url(self, filters: dict, page: int) -> str:
        intent   = filters.get("listing_type", "Buy").lower()
        location = filters.get("location", "").strip()

        if location:
            loc_slug  = location.lower().replace(" ", "-")
            base_path = f"https://www.realestate.com.au/{intent}/in-{loc_slug}/list-{page}"
        else:
            base_path = f"https://www.realestate.com.au/{intent}/list-{page}"

        params = {"activeSort": "relevance"}
        if filters.get("min_price"): params["minPrice"] = filters["min_price"]
        if filters.get("max_price"): params["maxPrice"] = filters["max_price"]
        if filters.get("min_beds"):  params["numBeds"]  = filters["min_beds"]
        if filters.get("min_baths"): params["numBaths"] = filters["min_baths"]

        ptype = filters.get("property_type", "Any")
        if ptype and ptype.lower() != "any":
            params["propertyType"] = ptype.lower()

        return f"{base_path}?{urlencode(params)}"

    # --------------------------------------------------------------------------
    # PRIMARY PARSER: __NEXT_DATA__ JSON
    # realestate.com.au is a Next.js app. All listing data is serialised into a
    # <script id="__NEXT_DATA__"> tag on page load — far more reliable than
    # scraping CSS classes which change on every deploy.
    # --------------------------------------------------------------------------
    def parse_next_data(self, html: str) -> list[dict]:
        soup   = BeautifulSoup(html, "html.parser")
        script = soup.find("script", id="__NEXT_DATA__")
        if not script or not script.string:
            return []

        try:
            raw        = json.loads(script.string)
            page_props = raw.get("props", {}).get("pageProps", {})

            # Try known paths through the pageProps tree
            results = (
                page_props.get("searchResults", {}).get("results", [])
                or page_props.get("listings", {}).get("results", [])
                or page_props.get("listingsMap", {}).get("results", [])
                or page_props.get("data", {}).get("results", [])
                or []
            )

            if not results:
                # Log top-level keys to help diagnose structure changes
                logging.warning(
                    f"[RealEstate] __NEXT_DATA__ found but no results at known paths. "
                    f"pageProps keys: {list(page_props.keys())}"
                )
                return []

            listings = []
            for item in results:
                try:
                    # Listings may be nested under a 'listing' key or at the top level
                    data = item.get("listing", item)

                    # Address
                    addr        = data.get("address", {})
                    street      = addr.get("streetAddress", "")
                    suburb      = addr.get("suburb", "")
                    state       = addr.get("state", "")
                    postcode    = addr.get("postcode", "")
                    address     = ", ".join(filter(None, [street, suburb, state, postcode]))
                    if not address:
                        address = data.get("headline", "Unknown Address")

                    # Price
                    price = (
                        data.get("priceDetails", {}).get("displayPrice")
                        or data.get("price", {}).get("display")
                        or "Contact Agent"
                    )

                    # Features
                    feats   = data.get("generalFeatures", {})
                    beds    = feats.get("bedrooms",     {}).get("value", "-")
                    baths   = feats.get("bathrooms",    {}).get("value", "-")
                    parking = feats.get("parkingSpaces",{}).get("value", "-")

                    # URL
                    url = data.get("listingUrl") or data.get("url") or ""
                    if url and not url.startswith("http"):
                        url = f"https://www.realestate.com.au{url}"

                    # Image
                    media   = data.get("media", {})
                    img_url = media.get("mainImage", {}).get("url", "")
                    if not img_url:
                        imgs    = media.get("images", [])
                        img_url = imgs[0].get("url", "") if imgs else ""

                    # Property type + land size
                    prop_type  = data.get("propertyType", {}).get("display", "Property")
                    land_label = ""
                    for feat in data.get("propertyFeatures", []):
                        if "land" in feat.get("category", "").lower():
                            land_label = f" • {feat.get('label', '')}"
                            break

                    if address and url:
                        listings.append({
                            "address": address,
                            "price":   price,
                            "beds":    str(beds),
                            "baths":   str(baths),
                            "parking": str(parking),
                            "type":    f"{prop_type}{land_label}",
                            "url":     url,
                            "image":   img_url,
                        })
                except Exception as e:
                    logging.warning(f"[RealEstate] Skipping malformed listing item: {e}")
                    continue

            return listings

        except Exception as e:
            logging.error(f"[RealEstate] Failed to parse __NEXT_DATA__: {e}")
            return []

    # --------------------------------------------------------------------------
    # FALLBACK PARSER: BeautifulSoup HTML
    # Used if __NEXT_DATA__ is absent or empty — less reliable but covers edge cases
    # --------------------------------------------------------------------------
    def parse_html(self, html: str) -> list[dict]:
        soup     = BeautifulSoup(html, "html.parser")
        cards    = soup.find_all("article") or soup.find_all("div", {"data-testid": "listing-card"})
        listings = []

        for card in cards:
            try:
                addr_tag = (
                    card.find(["h2", "a"], class_=lambda c: c and "address" in c.lower())
                    or card.find("a", href=lambda h: h and "/property-" in h)
                )
                if not addr_tag:
                    continue

                address  = addr_tag.get_text(strip=True)
                url_path = addr_tag.get("href", "")
                url      = f"https://www.realestate.com.au{url_path}" if url_path.startswith("/") else url_path

                price_tag = card.find(class_=lambda c: c and "price" in c.lower())
                price     = price_tag.get_text(strip=True) if price_tag else "Price on Application"

                beds = baths = parking = "-"
                for el in card.find_all(attrs={"aria-label": True}):
                    label = el["aria-label"].lower()
                    if "bedroom"  in label: beds    = label.split()[0]
                    elif "bathroom" in label: baths  = label.split()[0]
                    elif "parking" in label or "car" in label: parking = label.split()[0]

                img_tag = card.find("img")
                img_url = (img_tag.get("src") or img_tag.get("data-src") or "") if img_tag else ""

                ptype_tag = card.find(class_=lambda c: c and "property-type" in c.lower())
                prop_type = ptype_tag.get_text(strip=True) if ptype_tag else "Property"

                if address and url:
                    listings.append({
                        "address": address,
                        "price":   price,
                        "beds":    beds,
                        "baths":   baths,
                        "parking": parking,
                        "type":    prop_type,
                        "url":     url,
                        "image":   img_url,
                    })
            except Exception as e:
                logging.warning(f"[RealEstate] HTML parse error on card: {e}")
                continue

        return listings

    # --------------------------------------------------------------------------
    # SCRAPE ENGINE
    # --------------------------------------------------------------------------
    async def execute_scrape(self, filters: dict, max_results: int) -> tuple[list[dict], str]:
        all_listings  = []
        seen_urls     = set()
        status        = "Success"

        for page in range(1, 4):
            url = self.build_url(filters, page)
            logging.info(f"[RealEstate] Fetching page {page}: {url}")

            # Random human-like delay between page requests
            await asyncio.sleep(random.uniform(2.0, 4.5))

            try:
                response = await self.session.get(url, headers=SCRAPER_HEADERS)

                if response.status_code in (403, 429):
                    status = (
                        f"Cloudflare blocked the request (HTTP {response.status_code}). "
                        f"The site's bot protection rejected the scraper. "
                        f"Try again in a few minutes or provide a session cookie via `/realestate_config`."
                    )
                    break
                elif response.status_code != 200:
                    status = f"Unexpected HTTP {response.status_code} from realestate.com.au."
                    break

                # Try __NEXT_DATA__ first — most reliable
                page_listings = await self.bot.loop.run_in_executor(
                    None, self.parse_next_data, response.text
                )
                # Fall back to HTML parsing if Next.js data not found
                if not page_listings:
                    logging.info("[RealEstate] __NEXT_DATA__ empty — falling back to HTML parse.")
                    page_listings = await self.bot.loop.run_in_executor(
                        None, self.parse_html, response.text
                    )

                if not page_listings:
                    logging.info(f"[RealEstate] No listings on page {page} — stopping pagination.")
                    break

                for listing in page_listings:
                    if listing["url"] not in seen_urls:
                        seen_urls.add(listing["url"])
                        all_listings.append(listing)

                if len(all_listings) >= max_results:
                    break

            except Exception as e:
                logging.error(f"[RealEstate] Scrape error on page {page}: {e}")
                status = f"Scrape error: {e}"
                break

        return all_listings[:max_results], status

    # --------------------------------------------------------------------------
    # SHARED POST LOGIC
    # FIX: extracted from find_property so run_saved_search can call it
    # without double-defer errors (ctx is already deferred by the caller)
    # --------------------------------------------------------------------------
    async def _scrape_and_post(self, ctx: discord.ApplicationContext, filters: dict, max_results: int):
        listings, status = await self.execute_scrape(filters, max_results)

        # Resolve output channel
        target = ctx.channel
        thread_id = self.data.get("target_thread_id")
        if thread_id:
            try:
                resolved = await self.bot.fetch_channel(thread_id)
                if resolved:
                    target = resolved
            except Exception as e:
                logging.warning(f"[RealEstate] Could not resolve thread {thread_id}: {e}")

        send_to_thread = (target.id != ctx.channel.id)

        if not listings:
            embed = discord.Embed(
                title="🏠 No Properties Found",
                description=(
                    f"**Status:** {status}\n\n"
                    f"No results matched your filters. Try broadening your search."
                ),
                color=EMBED_COLOR
            )
            embed.add_field(name="Location",  value=filters.get("location")      or "Any", inline=True)
            embed.add_field(name="Type",       value=filters.get("listing_type")  or "Buy", inline=True)
            embed.add_field(name="Property",   value=filters.get("property_type") or "Any", inline=True)
            await ctx.respond(embed=embed)
            return

        total    = len(listings)
        summary  = (
            f"Showing **{total}** of **{total}** results."
            if total < max_results
            else f"Showing **{max_results}** results — refine your filters to narrow results."
        )
        header = f"🏠 **Real Estate Results** — {summary}"

        if send_to_thread:
            await target.send(header)
            await ctx.respond(f"Results posted to <#{target.id}>.", ephemeral=True)
        else:
            await ctx.respond(header)

        for listing in listings:
            embed = discord.Embed(
                title=listing["address"],
                description=(
                    f"**{listing['price']}**\n\n"
                    f"🛏️ {listing['beds']}   |   🚿 {listing['baths']}   |   🚗 {listing['parking']}"
                ),
                url=listing["url"],
                color=EMBED_COLOR
            )
            if listing["image"] and listing["image"].startswith("http"):
                embed.set_thumbnail(url=listing["image"])
            embed.set_footer(text=listing["type"])

            view = discord.ui.View()
            view.add_item(discord.ui.Button(label="View Listing", url=listing["url"], style=discord.ButtonStyle.link))

            try:
                await target.send(embed=embed, view=view)
            except discord.HTTPException as e:
                logging.error(f"[RealEstate] Failed to send embed: {e}")

            await asyncio.sleep(0.5)

    # --------------------------------------------------------------------------
    # COMMANDS
    # --------------------------------------------------------------------------
    @discord.slash_command(name="find_property", description="Scrape realestate.com.au for property listings")
    async def find_property(
        self,
        ctx: discord.ApplicationContext,
        location:      Option(str, "Suburb, postcode or region e.g. 'Bondi Beach' or '2026'", required=False, default=""),
        listing_type:  Option(str, "Intent", choices=["Buy", "Rent", "Sold"], required=False, default="Buy"),
        min_price:     Option(int, "Minimum price / weekly rent", required=False, default=None),
        max_price:     Option(int, "Maximum price / weekly rent", required=False, default=None),
        min_beds:      Option(int, "Minimum bedrooms",  min_value=1, required=False, default=None),
        min_baths:     Option(int, "Minimum bathrooms", min_value=1, required=False, default=None),
        property_type: Option(str, "Property type", choices=["House", "Apartment", "Townhouse", "Land", "Any"], required=False, default="Any"),
        max_results:   Option(int, "Max results (default 10, max 25)", min_value=1, max_value=25, required=False, default=10),
    ):
        await ctx.defer()
        filters = {
            "location":      location,
            "listing_type":  listing_type,
            "min_price":     min_price,
            "max_price":     max_price,
            "min_beds":      min_beds,
            "min_baths":     min_baths,
            "property_type": property_type,
        }
        await self._scrape_and_post(ctx, filters, max_results)

    @discord.slash_command(name="realestate_config", description="[Admin] Set the default output thread/channel")
    async def realestate_config(
        self,
        ctx:       discord.ApplicationContext,
        thread_id: Option(str, "Thread or Channel ID — leave blank to clear", required=False, default=None),
    ):
        if ctx.author.id != ADMIN_ID:
            return await ctx.respond("⛔ Restricted.", ephemeral=True)

        if thread_id:
            try:
                parsed = int(thread_id)
                self.data["target_thread_id"] = parsed
                save_data(self.data)
                await ctx.respond(f"✅ Output thread set to `{parsed}`.", ephemeral=True)
            except ValueError:
                await ctx.respond("❌ Invalid ID — must be an integer.", ephemeral=True)
        else:
            self.data["target_thread_id"] = None
            save_data(self.data)
            await ctx.respond("✅ Output thread cleared — results will post in the command channel.", ephemeral=True)

    @discord.slash_command(name="save_search", description="Save a filter set to re-run later")
    async def save_search(
        self,
        ctx:           discord.ApplicationContext,
        name:          Option(str, "Name for this saved search", required=True),
        location:      Option(str, "Suburb, postcode or region", required=False, default=""),
        listing_type:  Option(str, "Intent", choices=["Buy", "Rent", "Sold"], required=False, default="Buy"),
        min_price:     Option(int, "Minimum price / weekly rent", required=False, default=None),
        max_price:     Option(int, "Maximum price / weekly rent", required=False, default=None),
        min_beds:      Option(int, "Minimum bedrooms",  min_value=1, required=False, default=None),
        min_baths:     Option(int, "Minimum bathrooms", min_value=1, required=False, default=None),
        property_type: Option(str, "Property type", choices=["House", "Apartment", "Townhouse", "Land", "Any"], required=False, default="Any"),
    ):
        filters = {
            "location":      location,
            "listing_type":  listing_type,
            "min_price":     min_price,
            "max_price":     max_price,
            "min_beds":      min_beds,
            "min_baths":     min_baths,
            "property_type": property_type,
        }
        self.data.setdefault("saved_searches", {})[name] = filters
        save_data(self.data)
        await ctx.respond(f"✅ Saved search **{name}**.", ephemeral=True)

    @discord.slash_command(name="run_saved_search", description="Run a previously saved search")
    async def run_saved_search(
        self,
        ctx:         discord.ApplicationContext,
        name:        Option(str, "Saved search name", autocomplete=saved_search_autocomplete, required=True),
        max_results: Option(int, "Max results (default 10, max 25)", min_value=1, max_value=25, required=False, default=10),
    ):
        filters = self.data.get("saved_searches", {}).get(name)
        if not filters:
            return await ctx.respond(f"❌ No saved search named **{name}**.", ephemeral=True)

        await ctx.defer()
        # FIX: call _scrape_and_post directly — not find_property — to avoid double defer
        await self._scrape_and_post(ctx, filters, max_results)

    @discord.slash_command(name="list_searches", description="List all saved searches and their filters")
    async def list_searches(self, ctx: discord.ApplicationContext):
        searches = self.data.get("saved_searches", {})
        if not searches:
            return await ctx.respond("📝 No saved searches yet.", ephemeral=True)

        embed = discord.Embed(title="📋 Saved Real Estate Searches", color=EMBED_COLOR)
        for name, f in searches.items():
            price_range = f"{f.get('min_price') or '0'} – {f.get('max_price') or 'Any'}"
            desc = (
                f"**Location:** {f.get('location') or 'Any'}  |  **Intent:** {f.get('listing_type')}\n"
                f"**Price:** {price_range}  |  **Type:** {f.get('property_type') or 'Any'}\n"
                f"🛏️ {f.get('min_beds') or 'Any'}  |  🚿 {f.get('min_baths') or 'Any'}"
            )
            embed.add_field(name=name, value=desc, inline=False)

        await ctx.respond(embed=embed, ephemeral=True)

    @discord.slash_command(name="delete_search", description="Delete a saved search")
    async def delete_search(
        self,
        ctx:  discord.ApplicationContext,
        name: Option(str, "Search to delete", autocomplete=saved_search_autocomplete, required=True),
    ):
        if name in self.data.get("saved_searches", {}):
            del self.data["saved_searches"][name]
            save_data(self.data)
            await ctx.respond(f"🗑️ Deleted saved search **{name}**.", ephemeral=True)
        else:
            await ctx.respond(f"❌ No saved search named **{name}**.", ephemeral=True)


def setup(bot: discord.Bot):
    bot.add_cog(RealEstate(bot))
