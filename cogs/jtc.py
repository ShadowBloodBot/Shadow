# cogs/jtc.py
import json
import asyncio
import logging
from typing import Dict

import discord
from discord import ButtonStyle, SelectOption, Interaction
from discord.ui import View, Button, Modal, TextInput, Select
from discord.ext import commands, tasks
from discord.utils import get

from cogs.guild_registry import ch_id, is_registered_guild, PERSIST_ROOT

logger = logging.getLogger("ShadowSyn.JTC")

# --- CONSTANTS ---
THEME_PRIMARY             = 0x2B0B35
ROLE_ADMIN_ID             = 1214794734770323466
MASTER_OWNERS             = [132451058961219584, 482463400929263627]
VC_DEFAULT_BITRATE        = 64000

# --- PERSISTENCE ---
ACTIVE_VCS_STORE = PERSIST_ROOT / "active_vcs.json"

def _atomic_write(file_path, data):
    try:
        content  = json.dumps(data, indent=2)
        tmp_path = file_path.with_suffix(".tmp")
        tmp_path.write_text(content, encoding="utf-8")
        tmp_path.replace(file_path)
    except Exception as e:
        logger.error("Persistence Error [%s]: %s", file_path.name, e)

def _load_active_vcs() -> Dict[int, int]:
    if ACTIVE_VCS_STORE.exists():
        try:
            data = json.loads(ACTIVE_VCS_STORE.read_text(encoding="utf-8"))
            if isinstance(data, list):
                logger.warning("JTC: Migrating active_vcs.json from old list format.")
                return {int(cid): 0 for cid in data}
            elif isinstance(data, dict):
                return {int(k): v for k, v in data.items()}
        except Exception as e:
            logger.error("JTC: Failed to load active VCs — starting fresh: %s", e)
    return {}

def _save_active_vcs(vcs: Dict[int, int]) -> None:
    _atomic_write(ACTIVE_VCS_STORE, {str(k): v for k, v in vcs.items()})

# --- HELPERS ---
def _to_sans_bold_italic(text: str) -> str:
    _map = {
        "A": "𝘼", "B": "𝘽", "C": "𝘾", "D": "𝘿", "E": "𝙀", "F": "𝙁", "G": "𝙂",
        "H": "𝙃", "I": "𝙄", "J": "𝙅", "K": "𝙆", "L": "𝙇", "M": "𝙈", "N": "𝙉",
        "O": "𝙊", "P": "𝙋", "Q": "𝙌", "R": "𝙍", "S": "𝙎", "T": "𝙏", "U": "𝙐",
        "V": "𝙑", "W": "𝙒", "X": "𝙓", "Y": "𝙔", "Z": "𝙕", "a": "𝙖", "b": "𝙗",
        "c": "𝙘", "d": "𝙙", "e": "𝙚", "f": "𝙛", "g": "𝙜", "h": "𝙝", "i": "𝙞",
        "j": "𝙟", "k": "𝙠", "l": "𝙡", "m": "𝙢", "n": "𝙣", "o": "𝙤", "p": "𝙥",
        "q": "𝙦", "r": "𝙧", "s": "s",  "t": "𝙩", "u": "𝙪", "v": "𝙫", "w": "𝙬",
        "x": "𝙭", "y": "𝙮", "z": "𝙯"
    }
    return "".join(_map.get(ch, ch) for ch in text)

def _limit_channel_name(name: str, limit: int = 100) -> str:
    return name[:limit] if len(name) > limit else name

# =============================================================================
# UI COMPONENTS
# =============================================================================

class VCNameModal(Modal):
    def __init__(self, vc: discord.VoiceChannel):
        super().__init__(title="Rename Voice Channel")
        self.vc = vc
        self.add_item(TextInput(label="New VC Name", placeholder="Enter name...", required=True, max_length=50))

    async def callback(self, interaction: Interaction):
        try:
            new_name = _limit_channel_name(_to_sans_bold_italic(self.children[0].value))
            await self.vc.edit(name=new_name)
            await interaction.response.send_message("✅ Renamed.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Failed: {e}", ephemeral=True)

class KickMemberDropdown(Select):
    def __init__(self, vc: discord.VoiceChannel, members):
        self.vc = vc
        options = [SelectOption(label=m.display_name, value=str(m.id)) for m in members]
        super().__init__(placeholder="Select member to kick...", options=options, min_values=1, max_values=1)

    async def callback(self, interaction: Interaction):
        try:
            member = self.vc.guild.get_member(int(self.values[0]))
            if member and member in self.vc.members:
                await member.move_to(None)
                await interaction.response.send_message(f"👢 Kicked {member.display_name}.", ephemeral=True)
            else:
                await interaction.response.send_message("⚠️ Member not found in channel.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Failed: {e}", ephemeral=True)

class KickMemberView(View):
    def __init__(self, vc: discord.VoiceChannel, members):
        super().__init__(timeout=30)
        self.add_item(KickMemberDropdown(vc, members))

class RoleRestrictSelect(Select):
    def __init__(self, vc: discord.VoiceChannel, creator_id: int):
        self.vc         = vc
        self.creator_id = creator_id

        options = [SelectOption(label="🌐 Everyone (remove restriction)", value="everyone")]
        roles   = sorted(
            [r for r in vc.guild.roles if r != vc.guild.default_role and not r.managed],
            key=lambda r: r.position, reverse=True
        )[:24]
        for r in roles:
            options.append(SelectOption(label=(r.name or "Role")[:100], value=str(r.id)))

        super().__init__(
            placeholder="Select a role to restrict to...",
            options=options,
            min_values=1,
            max_values=1
        )

    async def callback(self, interaction: Interaction):
        if interaction.user.id != self.creator_id:
            return await interaction.response.send_message("🚫 Only the creator can restrict this channel.", ephemeral=True)
        try:
            if self.values[0] == "everyone":
                await self.vc.set_permissions(interaction.guild.default_role, connect=None)
                if self.vc.category:
                    for target, overwrite in self.vc.category.overwrites.items():
                        if isinstance(target, discord.Role) and target != interaction.guild.default_role:
                            await self.vc.set_permissions(target, connect=None)
                await interaction.response.send_message("✅ Restriction cleared — open to everyone.", ephemeral=True)
            else:
                role = interaction.guild.get_role(int(self.values[0]))
                if role:
                    await self.vc.set_permissions(interaction.guild.default_role, connect=False)
                    await self.vc.set_permissions(role, connect=True)
                    creator = interaction.guild.get_member(self.creator_id)
                    if creator:
                        await self.vc.set_permissions(creator, connect=True)
                    for oid in MASTER_OWNERS:
                        owner = interaction.guild.get_member(oid)
                        if owner:
                            await self.vc.set_permissions(owner, connect=True)
                    if self.vc.category:
                        for target, overwrite in self.vc.category.overwrites.items():
                            if (isinstance(target, discord.Role)
                                    and target != interaction.guild.default_role
                                    and target.id != role.id
                                    and not target.permissions.administrator):
                                await self.vc.set_permissions(target, connect=False)
                    await interaction.response.send_message(f"🔐 Restricted to **{role.name}**.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Failed: {e}", ephemeral=True)

class RoleRestrictView(View):
    def __init__(self, vc: discord.VoiceChannel, creator_id: int):
        super().__init__(timeout=60)
        self.add_item(RoleRestrictSelect(vc, creator_id))

class VCControlPanel(View):
    def __init__(self, vc: discord.VoiceChannel, creator_id: int, cog: 'JTCCog'):
        super().__init__(timeout=None)
        self.vc         = vc
        self.creator_id = creator_id
        self.cog        = cog
        vid             = str(vc.id)

        btn_defs = [
            ("🔒 Lock",   ButtonStyle.danger,  f"jtc_lock_{vid}",     self._lock),
            ("🔓 Unlock",   ButtonStyle.success, f"jtc_unlock_{vid}",   self._unlock),
            ("❌ Delete",   ButtonStyle.red,     f"jtc_delete_{vid}",   self._delete),
            ("✏️ Rename",   ButtonStyle.blurple, f"jtc_rename_{vid}",   self._rename),
            ("👢 Kick",     ButtonStyle.gray,    f"jtc_kick_{vid}",     self._kick),
        ]
        for label, style, cid, cb in btn_defs:
            btn          = Button(label=label, style=style, custom_id=cid)
            btn.callback = cb
            self.add_item(btn)

        btn_restrict          = Button(
            label="🔐 Restrict to Role",
            style=ButtonStyle.gray,
            custom_id=f"jtc_restrict_{vid}"
        )
        btn_restrict.callback = self._restrict
        self.add_item(btn_restrict)

        s_bitrate          = Select(
            placeholder="Bitrate",
            options=[SelectOption(label="64k", value="64000"), SelectOption(label="384k", value="384000")],
            custom_id=f"jtc_bitrate_{vid}"
        )
        s_bitrate.callback = self._bitrate
        self.add_item(s_bitrate)

        s_limit            = Select(
            placeholder="User Limit",
            options=[
                SelectOption(label="Unlimited", value="0"),
                SelectOption(label="5",         value="5"),
                SelectOption(label="10",        value="10"),
            ],
            custom_id=f"jtc_limit_{vid}"
        )
        s_limit.callback   = self._limit
        self.add_item(s_limit)

    async def _check(self, i: Interaction) -> bool:
        if i.user.id == self.creator_id:
            return True
        if i.data.get("custom_id") == f"jtc_delete_{self.vc.id}":
            if any(r.id == ROLE_ADMIN_ID for r in i.user.roles):
                return True
        await i.response.send_message("🚫 Only the channel creator can do that.", ephemeral=True)
        return False

    async def _lock(self, i: Interaction):
        if not await self._check(i): return
        await i.response.defer(ephemeral=True)
        try:
            _sem = asyncio.Semaphore(3)

            async def _set(target, **kwargs):
                async with _sem:
                    await self.vc.set_permissions(target, **kwargs)

            tasks = []
            for m in self.vc.members:
                tasks.append(_set(m, connect=True, speak=True))
            for oid in MASTER_OWNERS:
                owner = i.guild.get_member(oid)
                if owner and owner not in self.vc.members:
                    tasks.append(_set(owner, connect=True, speak=True))
            tasks.append(_set(i.guild.default_role, connect=False))
            if self.vc.category:
                for target, overwrite in self.vc.category.overwrites.items():
                    if isinstance(target, discord.Role) and target != i.guild.default_role and not target.permissions.administrator:
                        tasks.append(_set(target, connect=False))
            await asyncio.gather(*tasks)
            await i.followup.send("🔒 Locked.", ephemeral=True)
        except Exception as e:
            await i.followup.send(f"❌ Failed to lock: {e}", ephemeral=True)

    async def _unlock(self, i: Interaction):
        if not await self._check(i): return
        await i.response.defer(ephemeral=True)
        try:
            _sem = asyncio.Semaphore(3)

            async def _clear(target):
                async with _sem:
                    await self.vc.set_permissions(target, overwrite=None)

            tasks = [_clear(i.guild.default_role)]
            for target in list(self.vc.overwrites.keys()):
                if isinstance(target, discord.Member):
                    tasks.append(_clear(target))
                elif isinstance(target, discord.Role) and target != i.guild.default_role:
                    tasks.append(_clear(target))
            await asyncio.gather(*tasks)
            await i.followup.send("🔓 Unlocked.", ephemeral=True)
        except Exception as e:
            await i.followup.send(f"❌ Failed to unlock: {e}", ephemeral=True)

    async def _delete(self, i: Interaction):
        if not await self._check(i): return
        try:
            await self.vc.delete()
        except discord.NotFound:
            pass
        except Exception as e:
            return await i.response.send_message(f"❌ Failed to delete: {e}", ephemeral=True)
        self.cog.active_temp_vcs.pop(self.vc.id, None)
        _save_active_vcs(self.cog.active_temp_vcs)
        await i.response.send_message("🗑️ Deleted.", ephemeral=True)

    async def _rename(self, i: Interaction):
        if not await self._check(i): return
        await i.response.send_modal(VCNameModal(self.vc))

    async def _kick(self, i: Interaction):
        if not await self._check(i): return
        members = [m for m in self.vc.members if m != i.guild.me]
        if not members:
            return await i.response.send_message("⚠️ No one to kick.", ephemeral=True)
        await i.response.send_message("Select a member to kick:", view=KickMemberView(self.vc, members), ephemeral=True)

    async def _restrict(self, i: Interaction):
        if not await self._check(i): return
        try:
            view = RoleRestrictView(self.vc, self.creator_id)
            await i.response.send_message(
                "Select a role to restrict this channel to:",
                view=view,
                ephemeral=True
            )
        except Exception as e:
            await i.response.send_message(f"❌ Failed: {e}", ephemeral=True)

    async def _bitrate(self, i: Interaction):
        if not await self._check(i): return
        try:
            await self.vc.edit(bitrate=int(i.data["values"][0]))
            await i.response.send_message("📶 Bitrate updated.", ephemeral=True)
        except Exception as e:
            await i.response.send_message(f"❌ Failed: {e}", ephemeral=True)

    async def _limit(self, i: Interaction):
        if not await self._check(i): return
        try:
            await self.vc.edit(user_limit=int(i.data["values"][0]))
            await i.response.send_message("👥 User limit updated.", ephemeral=True)
        except Exception as e:
            await i.response.send_message(f"❌ Failed: {e}", ephemeral=True)

# =============================================================================
# COG
# =============================================================================

class JTCCog(commands.Cog):
    def __init__(self, bot):
        self.bot             = bot
        self.active_temp_vcs = _load_active_vcs()
        self._startup_done   = False
        self._panel_tasks: set = set()

    @commands.Cog.listener()
    async def on_ready(self):
        if self._startup_done:
            return
        self._startup_done = True
        await self._startup_cleanup()
        if not self._vc_sweep.is_running():
            self._vc_sweep.start()

    async def _startup_cleanup(self):
        to_remove = []
        restored  = 0

        for channel_id, creator_id in list(self.active_temp_vcs.items()):
            channel = self.bot.get_channel(channel_id)
            if channel is None:
                try:
                    channel = await self.bot.fetch_channel(channel_id)
                except discord.NotFound:
                    to_remove.append(channel_id)
                    continue
                except Exception as e:
                    logger.warning("JTC: Could not fetch channel %s: %s", channel_id, e)
                    continue

            if len(channel.members) == 0:
                try:
                    await channel.delete()
                except Exception:
                    pass
                to_remove.append(channel_id)
                continue

            if creator_id:
                view = VCControlPanel(channel, creator_id, self)
                self.bot.add_view(view)
                restored += 1

        for cid in to_remove:
            self.active_temp_vcs.pop(cid, None)
        if to_remove:
            _save_active_vcs(self.active_temp_vcs)

        logger.info("JTC: %d panel(s) restored, %d stale VC(s) cleaned up.", restored, len(to_remove))

        orphan_del, orphan_add = await self._sweep_category_orphans()
        if orphan_del or orphan_add:
            logger.info("JTC: orphan sweep — %d deleted, %d adopted.", orphan_del, orphan_add)

    async def _auto_grant_locked_vc(self, member: discord.Member, vc: discord.VoiceChannel) -> None:
        """Grant connect+speak to a member who was force-moved into a locked temp VC."""
        try:
            everyone_ow = vc.overwrites_for(vc.guild.default_role)
            if everyone_ow.connect is not False:
                return
            existing = vc.overwrites_for(member)
            if existing.connect is True:
                return
            await vc.set_permissions(member, connect=True, speak=True)
        except Exception as exc:
            logger.warning("JTC: auto-grant on locked join failed for %s: %s", member.id, exc)

    async def _auto_revoke_locked_vc(self, member: discord.Member, vc: discord.VoiceChannel) -> None:
        """Remove the explicit overwrite for a member who left a locked temp VC."""
        try:
            everyone_ow = vc.overwrites_for(vc.guild.default_role)
            if everyone_ow.connect is not False:
                return
            existing = vc.overwrites_for(member)
            if existing.connect is True:
                await vc.set_permissions(member, overwrite=None)
        except Exception as exc:
            logger.warning("JTC: auto-revoke on locked leave failed for %s: %s", member.id, exc)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        guild = member.guild
        if not is_registered_guild(guild.id):
            return

        jtc_id = ch_id(guild.id, "jtc")
        vc_cat_id = ch_id(guild.id, "vc_category")

        # Auto-grant connect+speak when someone joins a locked temp VC.
        # Covers the admin-force-move case where @everyone has connect=False
        # but no explicit overwrite was added for the moved member.
        if (after.channel
                and after.channel.id in self.active_temp_vcs
                and (not jtc_id or after.channel.id != jtc_id)):
            await self._auto_grant_locked_vc(member, after.channel)

        # Clean up the member-level overwrite when they leave a locked temp VC.
        if (before.channel
                and before.channel.id in self.active_temp_vcs
                and before.channel != after.channel
                and len(before.channel.members) > 0):
            await self._auto_revoke_locked_vc(member, before.channel)

        if after.channel and jtc_id and after.channel.id == jtc_id:
            try:
                cat    = get(guild.categories, id=vc_cat_id) or after.channel.category
                new_vc = await guild.create_voice_channel(
                    name=_limit_channel_name(_to_sans_bold_italic(f"{member.display_name}'s Room")),
                    category=cat,
                    bitrate=VC_DEFAULT_BITRATE
                )
                await new_vc.set_permissions(member, connect=True, speak=True)
                self.active_temp_vcs[new_vc.id] = member.id
                _save_active_vcs(self.active_temp_vcs)

                try:
                    await member.move_to(new_vc)
                except Exception as e:
                    logger.warning("JTC: move_to failed for %s — deleting orphaned VC: %s", member.display_name, e)
                    try:
                        await new_vc.delete()
                    except Exception:
                        pass
                    self.active_temp_vcs.pop(new_vc.id, None)
                    _save_active_vcs(self.active_temp_vcs)
                    return

                async def send_control_panel(vc: discord.VoiceChannel, creator_id: int):
                    await asyncio.sleep(1)
                    embed = discord.Embed(
                        title="🎛️ Voice Control",
                        description=f"Manage **{vc.name}**",
                        color=THEME_PRIMARY
                    )
                    try:
                        view = VCControlPanel(vc, creator_id, self)
                        await vc.send(embed=embed, view=view)
                        self.bot.add_view(view)
                    except Exception as e:
                        logger.warning("JTC: Failed to send control panel: %s", e)

                task = asyncio.create_task(send_control_panel(new_vc, member.id))
                self._panel_tasks.add(task)
                task.add_done_callback(self._panel_tasks.discard)

            except Exception as e:
                logger.error("JTC: VC creation failed for %s: %s", member.display_name, e)

        if (before.channel
                and before.channel.id in self.active_temp_vcs
                and len(before.channel.members) == 0):
            try:
                await before.channel.delete()
            except discord.NotFound:
                pass
            except Exception as e:
                logger.warning("JTC: Cleanup delete failed for channel %s: %s", before.channel.id, e)
            finally:
                self.active_temp_vcs.pop(before.channel.id, None)
                _save_active_vcs(self.active_temp_vcs)

    async def _sweep_category_orphans(self) -> tuple[int, int]:
        """Scan every vc_category for voice channels not in active_temp_vcs.

        Returns (deleted, adopted):
          deleted — empty orphans that were removed.
          adopted — occupied orphans added to tracking (creator_id=0).
        """
        deleted = 0
        adopted = 0
        changed = False

        for guild in self.bot.guilds:
            if not is_registered_guild(guild.id):
                continue
            jtc_trigger_id = ch_id(guild.id, "jtc")
            vc_cat_id      = ch_id(guild.id, "vc_category")
            if not vc_cat_id:
                continue
            category = guild.get_channel(vc_cat_id)
            if not isinstance(category, discord.CategoryChannel):
                continue
            for vc in category.voice_channels:
                if jtc_trigger_id and vc.id == jtc_trigger_id:
                    continue
                if vc.id in self.active_temp_vcs:
                    continue
                if len(vc.members) == 0:
                    try:
                        await vc.delete()
                        deleted += 1
                        changed = True
                    except Exception:
                        pass
                else:
                    self.active_temp_vcs[vc.id] = 0
                    adopted += 1
                    changed = True

        if changed:
            _save_active_vcs(self.active_temp_vcs)
        return deleted, adopted

    @tasks.loop(minutes=10)
    async def _vc_sweep(self):
        orphan_del, orphan_add = await self._sweep_category_orphans()

        # Also clear any tracked-but-now-empty channels missed by leave events.
        stale = []
        for cid in list(self.active_temp_vcs):
            channel = self.bot.get_channel(cid)
            if channel is None:
                stale.append(cid)
                continue
            if len(channel.members) == 0:
                try:
                    await channel.delete()
                except Exception:
                    pass
                stale.append(cid)
        for cid in stale:
            self.active_temp_vcs.pop(cid, None)
        if stale:
            _save_active_vcs(self.active_temp_vcs)

        if orphan_del or orphan_add or stale:
            logger.info(
                "JTC sweep: %d orphan deleted, %d orphan adopted, %d stale cleared.",
                orphan_del, orphan_add, len(stale)
            )

    @_vc_sweep.before_loop
    async def _before_vc_sweep(self):
        await self.bot.wait_until_ready()


def setup(bot):
    bot.add_cog(JTCCog(bot))
