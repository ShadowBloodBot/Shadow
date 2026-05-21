import os
import json
import base64
import logging
import sys
import aiohttp
import discord
from discord.ext import commands
from discord.commands import slash_command

# Initialize Standard Output Telemetry
logger = logging.getLogger("ShadowSyn")
logger.setLevel(logging.INFO)
stdout_handler = logging.StreamHandler(sys.stdout)
stdout_handler.setFormatter(logging.Formatter('[%(asctime)s] [%(levelname)s] %(message)s'))
logger.addHandler(stdout_handler)

class ShadowSynOracle(commands.Cog):
    """
    ShadowSyn Oracle: Advanced Multi-Modal Systems Intelligence & Analytics Engine.
    Leverages Gemini's long-context and multimodal reasoning architecture to ingest
    complex payloads (logs, data structures, images) and synthesize high-leverage strategic outputs.
    """
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.persist_dir = os.getenv("PERSIST_PATH", "/data")
        self.state_file = os.path.join(self.persist_dir, "oracle_state.json")
        self.api_key = os.getenv("GEMINI_API_KEY")
        self.api_url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-pro:generateContent"
        
        self._initialize_persistence()
        self.state = self._load_state()

    def _initialize_persistence(self):
        """Guarantees the persistence directory exists without throwing IO exceptions."""
        try:
            if not os.path.exists(self.persist_dir):
                os.makedirs(self.persist_dir, exist_ok=True)
                logger.info(f"Created persistent directory at {self.persist_dir}")
        except Exception as e:
            logger.error(f"Failed to initialize persistence directory: {str(e)}")

    def _load_state(self) -> dict:
        """Loads state with absolute fallback to clean data architecture."""
        if not os.path.exists(self.state_file):
            return {"analytics_history": [], "system_rules": []}
        try:
            with open(self.state_file, "r") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error reading state file, initializing clean state: {str(e)}")
            return {"analytics_history": [], "system_rules": []}

    def _atomic_save(self):
        """Enforces atomic write operations to prevent data corruption during runtime recycling."""
        temp_file = f"{self.state_file}.tmp"
        try:
            with open(temp_file, "w") as f:
                json.dump(self.state, f, indent=4)
            os.replace(temp_file, self.state_file)
        except Exception as e:
            logger.error(f"Atomic state save operation failed: {str(e)}")
            if os.path.exists(temp_file):
                os.remove(temp_file)

    async def _call_gemini(self, system_instruction: str, prompt: str, attachment_bytes: bytes = None, mime_type: str = None) -> str:
        """
        Executes asynchronous programmatic calls to the Gemini Core API.
        Handles multi-modal payloads via raw inline data components.
        """
        if not self.api_key:
            return "ERROR: GEMINI_API_KEY environmental variable is missing from the runtime container."

        headers = {"Content-Type": "application/json"}
        params = {"key": self.api_key}

        parts = [{"text": prompt}]
        if attachment_bytes and mime_type:
            base64_data = base64.b64encode(attachment_bytes).decode("utf-8")
            parts.append({
                "inline_data": {
                    "mime_type": mime_type,
                    "data": base64_data
                }
            })

        payload = {
            "contents": [{"parts": parts}],
            "systemInstruction": {
                "parts": [{"text": system_instruction}]
            },
            "generationConfig": {
                "temperature": 0.2,
                "maxOutputTokens": 8192
            }
        }

        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(self.api_url, headers=headers, params=params, json=payload, timeout=60) as response:
                    if response.status == 200:
                        response_data = await response.json()
                        return response_data["candidates"][0]["content"]["parts"][0]["text"]
                    else:
                        error_text = await response.text()
                        logger.error(f"Gemini API error call response code {response.status}: {error_text}")
                        return f"ERROR: Backend API execution failed with status code {response.status}."
            except Exception as e:
                logger.error(f"Exception during Gemini API network transportation: {str(e)}")
                return "ERROR: Internal transportation failure while processing analytical pipeline."

    oracle = discord.SlashCommandGroup("oracle", "Elite Intelligence and Multimodal Analytics Engine")

    @oracle.command(name="analyze", description="Pipes unstructured queries and multi-modal payloads into Gemini Core processing loops.")
    async def analyze(
        self, 
        ctx: discord.ApplicationContext, 
        query: discord.Option(str, "The core optimization or analytical query", required=True),
        document: discord.Option(discord.Attachment, "Document, logs, or image matrix data payload", required=False, default=None),
        deep_insights: discord.Option(bool, "Toggles advanced structural deep-dive frameworks", required=False, default=False)
    ):
        await ctx.defer()
        try:
            system_instruction = """You are the ShadowSyn System Oracle. Your cognitive matrix is tuned to elite systems analysis, extreme logic, mechanical precision, and structural optimization. Strip all superficial narrative fluff, platitudes, and conversational padding. Output raw, high-leverage insights, structural frameworks, or mathematical representations based strictly on the user input. Think in terms of systems, game theory, and leverage."""
            
            if deep_insights:
                system_instruction += " Enforce an advanced deep-dive framework tracing tertiary implications and hidden vectors."

            attachment_bytes = None
            mime_type = None

            if document:
                if document.size > 20971520:  # 20MB Threshold Safeguard
                    embed = discord.Embed(
                        title="System Constraint Violation",
                        description="Payload exceeds max size allocation limits (20MB). Execution halted.",
                        color=0x2B0B35
                    )
                    await ctx.respond(embed=embed, ephemeral=True)
                    return
                
                attachment_bytes = await document.read()
                mime_type = document.content_type

            raw_analysis = await self._call_gemini(system_instruction, query, attachment_bytes, mime_type)

            # Truncation safety logic mapping into standard Embed structural size parameters
            clean_output = raw_analysis if len(raw_analysis) <= 4000 else f"{raw_analysis[:3990]}\n\n[Output Truncated Due To Container Buffer Limits]"

            embed = discord.Embed(
                title="ShadowSyn Oracle System Analysis",
                color=0x2B0B35
            )
            embed.add_field(name="Input Matrix Query", value=query[:1024], inline=False)
            embed.description = f"```markdown\n{clean_output}\n```"
            
            # Persistent State Registration Tracking
            self.state["analytics_history"].append({
                "timestamp": ctx.interaction.created_at.isoformat(),
                "user_id": ctx.author.id,
                "query": query,
                "has_attachment": document is not None
            })
            if len(self.state["analytics_history"]) > 100: # Bound array growth to prevent memory leaks
                self.state["analytics_history"].pop(0)
            self._atomic_save()

            await ctx.respond(embed=embed)

        except Exception as e:
            logger.error(f"Execution crash in slash command 'analyze': {str(e)}")
            embed = discord.Embed(
                title="Execution Failure",
                description="The analytical core experienced a critical thread fault.",
                color=0x2B0B35
            )
            await ctx.respond(embed=embed, ephemeral=True)

    @oracle.command(name="telemetry", description="Displays persistence operational metrics and analytical cache status.")
    async def telemetry(self, ctx: discord.ApplicationContext):
        try:
            history_count = len(self.state.get("analytics_history", []))
            embed = discord.Embed(
                title="ShadowSyn Oracle Telemetry Matrix",
                color=0x2B0B35
            )
            embed.add_field(name="Data Persistence Path", value=f"`{self.state_file}`", inline=False)
            embed.add_field(name="Cached Operations Tracked", value=f"`{history_count}` runs", inline=True)
            embed.add_field(name="API Core Blueprint Target", value="`Gemini-2.5-Pro Engine Architecture`", inline=True)
            await ctx.respond(embed=embed, ephemeral=True)
        except Exception as e:
            logger.error(f"Execution crash in slash command 'telemetry': {str(e)}")
            embed = discord.Embed(
                title="Execution Failure",
                description="Unable to access internal state telemetry arrays.",
                color=0x2B0B35
            )
            await ctx.respond(embed=embed, ephemeral=True)

    @oracle.command(name="purge", description="Resets internal analytics historical cache metrics.")
    @commands.has_permissions(administrator=True)
    async def purge(self, ctx: discord.ApplicationContext):
        try:
            self.state["analytics_history"] = []
            self._atomic_save()
            embed = discord.Embed(
                title="Cache State Purged",
                description="Historical telemetry registers completely cleared. State file updated via atomic write sequence.",
                color=0x2B0B35
            )
            await ctx.respond(embed=embed, ephemeral=True)
        except Exception as e:
            logger.error(f"Execution crash in slash command 'purge': {str(e)}")
            embed = discord.Embed(
                title="Execution Failure",
                description="State manipulation failure encountered during purge array assignment.",
                color=0x2B0B35
            )
            await ctx.respond(embed=embed, ephemeral=True)

def setup(bot: commands.Bot):
    bot.add_cog(ShadowSynOracle(bot))
