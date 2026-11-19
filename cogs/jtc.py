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

from cogs.guild_registry import (
    ch_id,
    has_admin_shadow,
    is_registered_guild,
    resolve_channel,
    PERSIST_ROOT,
)

logger = logging.getLogger("ShadowSyn.JTC")

# --- CONSTANTS ---
THEME_PRIMARY             = 0x2B0B35
ROLE_ADMIN_ID             = 1214794734770323466
MASTER_OWNERS             = [132451058961219584, 482463400929263627]
# Creators whose rooms are hidden from everyone except themselves, MASTER_OWNERS
# and the bot. Guests only gain access when dragged in, and lose it on leave.
ISOLATED_CREATOR_IDS      = {480746585110740992}
VC_DEFAULT_BITRATE        = 64000
# Seconds to let a client finish connecting before the suppress heal re-moves it.
HEAL_SETTLE_SEC           = 1.0
# A room this young is still being set up (create -> move in flight). The
# sweeps skip it: an empty room seconds old is not an orphan.
NEW_ROOM_GRACE_SEC        = 30
# Wait before each attempt to create the room and move its creator into it.
MOVE_RETRY_DELAYS         = (0.0, 0.5, 1.5)
# How long the "couldn't open your room" notice stays in the trigger chat.
STRAND_NOTICE_TTL_SEC     = 30

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

def _is_new_room(channel) -> bool:
    age = (discord.utils.utcnow() - channel.created_at).total_seconds()
    return age < NEW_ROOM_GRACE_SEC

def _in_channel(member: discord.Member, channel_id: int) -> bool:
    voice = member.voice
    return bool(voice and voice.channel and voice.channel.id == channel_id)

def _describe_error(exc: BaseException) -> str:
    """Exception type plus Discord HTTP status/code — enough to tell causes apart."""
    text = (
        f"{type(exc).__name__} status={getattr(exc, 'status', None)} "
        f"code={getattr(exc, 'code', None)}: {exc}"
    )
    return text[:300]

def _is_isolated_creator(creator_id) -> bool:
    try:
        return int(creator_id) in ISOLATED_CREATOR_IDS
    except (TypeError, ValueError):
        return False

def _isolation_overwrites(guild: discord.Guild, creator, extra_members=()) -> dict:
    """Baseline overwrites for an isolated room.

    @everyone cannot see or connect. Creator, MASTER_OWNERS, the bot and any
    listed occupants are explicitly allowed. The bot entry matters on guilds
    where it is not Administrator (ShadowBackup) — without it the bot loses
    sight of its own channel.
    """
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False, connect=False),
    }
    if creator is not None:
        overwrites[creator] = discord.PermissionOverwrite(
            view_channel=True, connect=True, speak=True, move_members=True
        )
    for oid in MASTER_OWNERS:
        owner = guild.get_member(oid)
        if owner and owner not in overwrites:
            overwrites[owner] = discord.PermissionOverwrite(view_channel=True, connect=True, speak=True)
    if guild.me:
        overwrites[guild.me] = discord.PermissionOverwrite(
            view_channel=True, connect=True, speak=True,
            manage_channels=True, move_members=True, send_messages=True,
        )
    for m in extra_members:
        if m not in overwrites:
            overwrites[m] = discord.PermissionOverwrite(view_channel=True, connect=True, speak=True)
    return overwrites

# =============================================================================
# UI COMPONENTS
# =============================================================================

class VCNameModal(Modal):
    def __init__(self, vc: discord.VoiceChannel):
        super().__init__(title="Rename Voice Channel")
        self.vc = vc
        self.add_item(TextInput(label="New VC Name", placeholder="Enter name...", required=True, max_length=50))

    async def callback(self, interaction: Interaction):
        # Defer first — Discord rate-limits channel renames hard, so the edit
        # can sit well past the 3s interaction deadline.
        await interaction.response.defer(ephemeral=True)
        try:
            new_name = _limit_channel_name(_to_sans_bold_italic(self.children[0].value))
            await self.vc.edit(name=new_name)
            await interaction.followup.send("✅ Renamed.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Failed: {e}", ephemeral=True)

class KickMemberDropdown(Select):
    def __init__(self, vc: discord.VoiceChannel, members, creator_id: int = 0):
        self.vc = vc
        self.creator_id = creator_id
        options = [SelectOption(label=m.display_name, value=str(m.id)) for m in members]
        super().__init__(placeholder="Select member to kick...", options=options, min_values=1, max_values=1)

    async def _revoke_access(self, member: discord.Member) -> None:
        """Drop a kicked member's overwrite so a locked room stays closed to them.

        Creator, MASTER_OWNERS and the bot keep theirs.
        """
        guild = self.vc.guild
        if (member.id == self.creator_id
                or member.id in MASTER_OWNERS
                or (guild.me and member.id == guild.me.id)):
            return
        try:
            if member not in self.vc.overwrites:
                return
            await self.vc.set_permissions(member, overwrite=None, reason="JTC: kicked from room")
        except discord.NotFound:
            pass  # room was deleted because the kick emptied it
        except Exception as exc:
            logger.warning("JTC: kick revoke failed for %s in %s: %s", member.id, self.vc.id, exc)

    async def callback(self, interaction: Interaction):
        try:
            member = self.vc.guild.get_member(int(self.values[0]))
            if member and member in self.vc.members:
                await member.move_to(None)
                await interaction.response.send_message(f"👢 Kicked {member.display_name}.", ephemeral=True)
            else:
                return await interaction.response.send_message("⚠️ Member not found in channel.", ephemeral=True)
        except Exception as e:
            return await interaction.response.send_message(f"❌ Failed: {e}", ephemeral=True)
        # After the reply so a slow permission call cannot blow the 3s deadline.
        await self._revoke_access(member)

class KickMemberView(View):
    def __init__(self, vc: discord.VoiceChannel, members, creator_id: int = 0):
        super().__init__(timeout=30)
        self.add_item(KickMemberDropdown(vc, members, creator_id))

class RoleRestrictSelect(Select):
    """Native role select — searchable over every guild role, always current."""

    def __init__(self, vc: discord.VoiceChannel, creator_id: int):
        self.vc         = vc
        self.creator_id = creator_id
        super().__init__(
            select_type=discord.ComponentType.role_select,
            placeholder="Type a role name to search…",
            min_values=1,
            max_values=1
        )

    async def callback(self, interaction: Interaction):
        if interaction.user.id != self.creator_id:
            return await interaction.response.send_message("🚫 Only the creator can restrict this channel.", ephemeral=True)
        picked = self.values[0]
        role = picked if isinstance(picked, discord.Role) else interaction.guild.get_role(int(picked))
        if role is None:
            return await interaction.response.send_message("❌ Role not found.", ephemeral=True)
        if role == interaction.guild.default_role:
            return await interaction.response.send_message(
                "⚠️ Use the **🌐 Open to Everyone** button to clear the restriction.", ephemeral=True
            )
        if role.managed:
            return await interaction.response.send_message(
                "⚠️ Bot/integration roles can't be used for restriction.", ephemeral=True
            )
        # Defer immediately — the old serial set_permissions calls routinely
        # blew the 3s interaction deadline and died with Unknown interaction.
        await interaction.response.defer(ephemeral=True)
        try:
            overwrites = dict(self.vc.overwrites)

            def _merge(target, **perms):
                ow = overwrites.get(target) or discord.PermissionOverwrite()
                ow.update(**perms)
                overwrites[target] = ow

            _merge(interaction.guild.default_role, connect=False)
            _merge(role, connect=True)
            # Keep whoever is already inside (same as Lock). Without this they
            # keep talking until their next reconnect, then cannot speak or rejoin.
            isolated = _is_isolated_creator(self.creator_id)
            for m in self.vc.members:
                if isolated:
                    _merge(m, view_channel=True, connect=True, speak=True)
                else:
                    _merge(m, connect=True, speak=True)
            creator = interaction.guild.get_member(self.creator_id)
            if creator:
                _merge(creator, connect=True)
            for oid in MASTER_OWNERS:
                owner = interaction.guild.get_member(oid)
                if owner:
                    _merge(owner, connect=True)
            if self.vc.category:
                for target in self.vc.category.overwrites:
                    if (isinstance(target, discord.Role)
                            and target != interaction.guild.default_role
                            and target.id != role.id
                            and not target.permissions.administrator):
                        _merge(target, connect=False)

            # Single API call instead of 5-10 serial permission PATCHes.
            await self.vc.edit(overwrites=overwrites)
            await interaction.followup.send(f"🔐 Restricted to **{role.name}**.", ephemeral=True)
        except Exception as e:
            logger.warning("JTC: restrict-to-role failed for VC %s: %s", self.vc.id, e)
            try:
                await interaction.followup.send(f"❌ Failed: {e}", ephemeral=True)
            except Exception:
                pass

class RoleRestrictView(View):
    def __init__(self, vc: discord.VoiceChannel, creator_id: int):
        super().__init__(timeout=60)
        self.vc         = vc
        self.creator_id = creator_id
        self.add_item(RoleRestrictSelect(vc, creator_id))

        btn_open          = Button(label="🌐 Open to Everyone", style=ButtonStyle.success)
        btn_open.callback = self._open_everyone
        self.add_item(btn_open)

    async def _open_everyone(self, interaction: Interaction):
        if interaction.user.id != self.creator_id:
            return await interaction.response.send_message("🚫 Only the creator can restrict this channel.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        try:
            # Clear connect on every role overwrite in one edit call —
            # member overwrites (creator, kicked/granted users) are preserved.
            overwrites = {}
            for target, ow in self.vc.overwrites.items():
                if isinstance(target, discord.Role):
                    ow.update(connect=None)
                    if ow.is_empty():
                        continue
                overwrites[target] = ow
            await self.vc.edit(overwrites=overwrites)
            await interaction.followup.send("✅ Restriction cleared — open to everyone.", ephemeral=True)
        except Exception as e:
            logger.warning("JTC: open-to-everyone failed for VC %s: %s", self.vc.id, e)
            try:
                await interaction.followup.send(f"❌ Failed: {e}", ephemeral=True)
            except Exception:
                pass

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
            # Registry role, so the bypass works on both guilds.
            if has_admin_shadow(i.user, i.guild.id):
                return True
        await i.response.send_message("🚫 Only the channel creator can do that.", ephemeral=True)
        return False

    async def _lock(self, i: Interaction):
        if not await self._check(i): return
        await i.response.defer(ephemeral=True)
        try:
            overwrites = dict(self.vc.overwrites)

            def _merge(target, **perms):
                ow = overwrites.get(target) or discord.PermissionOverwrite()
                ow.update(**perms)
                overwrites[target] = ow

            isolated = _is_isolated_creator(self.creator_id)
            for m in self.vc.members:
                if isolated:
                    _merge(m, view_channel=True, connect=True, speak=True)
                else:
                    _merge(m, connect=True, speak=True)
            for oid in MASTER_OWNERS:
                owner = i.guild.get_member(oid)
                if owner and owner not in self.vc.members:
                    _merge(owner, connect=True, speak=True)
            _merge(i.guild.default_role, connect=False)
            if self.vc.category:
                for target, overwrite in self.vc.category.overwrites.items():
                    if isinstance(target, discord.Role) and target != i.guild.default_role and not target.permissions.administrator:
                        _merge(target, connect=False)
            await self.vc.edit(overwrites=overwrites)
            await i.followup.send("🔒 Locked.", ephemeral=True)
        except Exception as e:
            await i.followup.send(f"❌ Failed to lock: {e}", ephemeral=True)

    async def _unlock(self, i: Interaction):
        if not await self._check(i): return
        await i.response.defer(ephemeral=True)
        try:
            # One edit replaces every role/member overwrite (same targets as
            # the old per-target set_permissions(overwrite=None) loop).
            if _is_isolated_creator(self.creator_id):
                # Isolated rooms never open up — reset to the hidden baseline
                # while keeping whoever is currently inside.
                creator = i.guild.get_member(self.creator_id)
                await self.vc.edit(
                    overwrites=_isolation_overwrites(i.guild, creator, extra_members=self.vc.members)
                )
            else:
                await self.vc.edit(overwrites={})
            await i.followup.send("🔓 Unlocked.", ephemeral=True)
        except Exception as e:
            await i.followup.send(f"❌ Failed to unlock: {e}", ephemeral=True)

    async def _delete(self, i: Interaction):
        if not await self._check(i): return
        await i.response.defer(ephemeral=True)
        try:
            await self.vc.delete()
        except discord.NotFound:
            pass
        except Exception as e:
            return await i.followup.send(f"❌ Failed to delete: {e}", ephemeral=True)
        self.cog.active_temp_vcs.pop(self.vc.id, None)
        _save_active_vcs(self.cog.active_temp_vcs)
        try:
            await i.followup.send("🗑️ Deleted.", ephemeral=True)
        except discord.HTTPException:
            pass  # the panel's channel is the one that was just deleted

    async def _rename(self, i: Interaction):
        if not await self._check(i): return
        await i.response.send_modal(VCNameModal(self.vc))

    async def _kick(self, i: Interaction):
        if not await self._check(i): return
        members = [m for m in self.vc.members if m != i.guild.me]
        if not members:
            return await i.response.send_message("⚠️ No one to kick.", ephemeral=True)
        await i.response.send_message(
            "Select a member to kick:",
            view=KickMemberView(self.vc, members, self.creator_id),
            ephemeral=True,
        )

    async def _restrict(self, i: Interaction):
        if not await self._check(i): return
        try:
            view = RoleRestrictView(self.vc, self.creator_id)
            role_count = sum(
                1 for r in i.guild.roles
                if r != i.guild.default_role and not r.managed
            )
            embed = discord.Embed(
                title="Restrict to Role",
                description=(
                    "Discord only shows a short preview in the dropdown — **type the role name** "
                    "(e.g. `SAND`, `Rust`) to find any role in the server.\n\n"
                    "Pick the matching role from the filtered results.\n"
                    "Use **🌐 Open to Everyone** to clear a restriction."
                ),
                color=THEME_PRIMARY
            )
            embed.set_footer(text=f"{role_count} roles in server — search required for most")
            await i.response.send_message(embed=embed, view=view, ephemeral=True)
        except Exception as e:
            await i.response.send_message(f"❌ Failed: {e}", ephemeral=True)

    async def _bitrate(self, i: Interaction):
        if not await self._check(i): return
        await i.response.defer(ephemeral=True)
        try:
            await self.vc.edit(bitrate=int(i.data["values"][0]))
            await i.followup.send("📶 Bitrate updated.", ephemeral=True)
        except Exception as e:
            await i.followup.send(f"❌ Failed: {e}", ephemeral=True)

    async def _limit(self, i: Interaction):
        if not await self._check(i): return
        await i.response.defer(ephemeral=True)
        try:
            await self.vc.edit(user_limit=int(i.data["values"][0]))
            await i.followup.send("👥 User limit updated.", ephemeral=True)
        except Exception as e:
            await i.followup.send(f"❌ Failed: {e}", ephemeral=True)

# =============================================================================
# COG
# =============================================================================

class JTCCog(commands.Cog):
    def __init__(self, bot):
        self.bot             = bot
        self.active_temp_vcs = _load_active_vcs()
        self._startup_done   = False
        self._panel_tasks: set = set()
        self._healing: set   = set()
        self._creating: set  = set()   # member ids with a room creation in flight

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

            # A room seconds old belongs to a creation that is still in flight
            # (voice events are handled while startup runs) — leave it alone.
            if len(channel.members) == 0 and not _is_new_room(channel):
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

    async def _auto_grant_locked_vc(self, member: discord.Member, vc: discord.VoiceChannel) -> bool:
        """Grant connect+speak to a member who was force-moved into a locked temp VC.

        Returns True when an overwrite was actually written.
        """
        try:
            everyone_ow = vc.overwrites_for(vc.guild.default_role)
            hidden   = everyone_ow.view_channel is False
            if everyone_ow.connect is not False and not hidden:
                return False
            existing = vc.overwrites_for(member)
            if (existing.connect is True and existing.speak is True
                    and (not hidden or existing.view_channel is True)):
                return False
            grant = {"connect": True, "speak": True}
            if hidden:
                grant["view_channel"] = True
            await vc.set_permissions(member, **grant)
            return True
        except Exception as exc:
            logger.warning("JTC: auto-grant on locked join failed for %s: %s", member.id, exc)
            return False

    async def _revoke_isolated_guest(self, member: discord.Member, vc: discord.VoiceChannel) -> None:
        """Remove a guest's overwrite from an isolated room after they leave."""
        try:
            if member not in vc.overwrites:
                return
            await vc.set_permissions(member, overwrite=None, reason="JTC: isolated room guest left")
        except discord.NotFound:
            pass
        except Exception as exc:
            logger.warning("JTC: isolated revoke failed for %s in %s: %s", member.id, vc.id, exc)

    async def _heal_suppress(self, member: discord.Member, vc: discord.VoiceChannel) -> None:
        """Clear a stuck suppress voice-state by re-moving the member.

        Discord evaluates Speak at connect/move time. A member moved into a
        channel where Speak resolved to denied stays suppressed even after
        overwrites are granted — only a reconnect or another move clears it.
        """
        key = (member.id, vc.id)
        if key in self._healing:
            return
        self._healing.add(key)
        try:
            # Let the client finish connecting first. Re-moving mid-handshake
            # drops the voice connection, and Discord often clears suppress on
            # its own once the granted overwrite lands. This runs in a
            # background task, so the voice-state handler is never blocked.
            await asyncio.sleep(HEAL_SETTLE_SEC)
            voice = member.voice
            if not voice or not voice.channel or voice.channel.id != vc.id:
                return
            if not voice.suppress:
                return
            await member.move_to(vc, reason="JTC: clearing stuck voice suppression")
            await asyncio.sleep(1.0)
            voice = member.voice
            if voice and voice.channel and voice.channel.id == vc.id and voice.suppress:
                logger.warning("JTC: suppress heal did not clear for %s in %s.", member.id, vc.id)
            else:
                logger.info("JTC: cleared stuck suppress for %s in %s.", member.id, vc.id)
        except Exception as exc:
            logger.warning("JTC: suppress heal failed for %s: %s", member.id, exc)
        finally:
            self._healing.discard(key)

    async def _open_room(self, member: discord.Member, trigger, category) -> None:
        """Create a room for ``member`` and move them out of the trigger into it.

        The trigger only fires on arrival. A single failed move used to delete
        the room and leave the creator sitting in the trigger with no room and
        no message — everyone dragged "to them" then got split into rooms of
        their own. So: retry, and if it still fails, say so.
        """
        guild  = member.guild
        new_vc = None
        error  = None
        moved  = False

        for attempt, delay in enumerate(MOVE_RETRY_DELAYS, start=1):
            if delay:
                await asyncio.sleep(delay)
            if not _in_channel(member, trigger.id):
                break  # left the trigger (or voice) — nobody to move
            try:
                if new_vc is None:
                    if _is_isolated_creator(member.id):
                        room_overwrites = _isolation_overwrites(guild, member)
                    else:
                        room_overwrites = {
                            member: discord.PermissionOverwrite(connect=True, speak=True),
                        }
                    new_vc = await guild.create_voice_channel(
                        name=_limit_channel_name(_to_sans_bold_italic(f"{member.display_name}'s Room")),
                        category=category,
                        bitrate=VC_DEFAULT_BITRATE,
                        overwrites=room_overwrites,
                    )
                    self.active_temp_vcs[new_vc.id] = member.id
                    _save_active_vcs(self.active_temp_vcs)
                await member.move_to(new_vc)
                moved = True
                if attempt > 1:
                    logger.info("JTC: room for %s opened on attempt %d.", member.id, attempt)
                break
            except Exception as exc:
                error = exc
                logger.warning(
                    "JTC: room attempt %d/%d failed for %s (%s) — %s",
                    attempt, len(MOVE_RETRY_DELAYS), member.display_name, member.id,
                    _describe_error(exc),
                )
                # The room itself is gone (Unknown Channel) — make a new one next attempt.
                if new_vc is not None and (
                    getattr(exc, "code", None) == 10003
                    or guild.get_channel(new_vc.id) is None
                ):
                    self.active_temp_vcs.pop(new_vc.id, None)
                    _save_active_vcs(self.active_temp_vcs)
                    new_vc = None

        if not moved and new_vc is not None and _in_channel(member, new_vc.id):
            moved = True  # the move landed even though the call raised

        if not moved:
            if new_vc is not None:
                try:
                    await new_vc.delete()
                except discord.NotFound:
                    pass
                except Exception as exc:
                    logger.warning("JTC: could not delete unused room %s: %s", new_vc.id, exc)
                self.active_temp_vcs.pop(new_vc.id, None)
                _save_active_vcs(self.active_temp_vcs)
            if error is not None and _in_channel(member, trigger.id):
                await self._report_strand(member, trigger, error)
            return

        # Creator may have entered the lobby suppressed (dragged in,
        # or lacking a lobby Connect role) — the stuck state can carry
        # into the new room. Heal in the background.
        heal_task = asyncio.create_task(self._heal_suppress(member, new_vc))
        self._panel_tasks.add(heal_task)
        heal_task.add_done_callback(self._panel_tasks.discard)

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

    async def _report_strand(self, member: discord.Member, trigger, error: BaseException) -> None:
        """A creator is still in the trigger with no room — tell them and the audit trail."""
        detail = _describe_error(error)
        logger.error(
            "JTC: no room opened for %s (%s) after %d attempts — %s",
            member.display_name, member.id, len(MOVE_RETRY_DELAYS), detail,
        )
        try:
            notice = discord.Embed(
                description=(
                    f"⚠️ I couldn't open your room. Leave **{trigger.name}** and join it again."
                ),
                color=THEME_PRIMARY,
            )
            await trigger.send(
                content=member.mention,
                embed=notice,
                delete_after=STRAND_NOTICE_TTL_SEC,
                allowed_mentions=discord.AllowedMentions(users=[member]),
            )
        except Exception as exc:
            logger.warning("JTC: strand notice failed for %s: %s", member.id, exc)
        try:
            audit = await resolve_channel(self.bot, member.guild.id, "voice_audit")
            if audit:
                embed = discord.Embed(
                    title="⚠️ JTC room not opened",
                    description=(
                        f"{member.mention} was left in **{trigger.name}** — "
                        f"{len(MOVE_RETRY_DELAYS)} attempts failed.\n`{detail}`"
                    ),
                    color=THEME_PRIMARY,
                )
                embed.set_footer(text=f"User ID: {member.id}")
                await audit.send(embed=embed)
        except Exception as exc:
            logger.warning("JTC: strand audit post failed for %s: %s", member.id, exc)

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
        # Only on actual channel joins (not mute/deaf toggles) so the
        # suppress heal's re-move cannot re-trigger this path.
        if (after.channel
                and after.channel.id in self.active_temp_vcs
                and (before.channel is None or before.channel.id != after.channel.id)
                and (not jtc_id or after.channel.id != jtc_id)):
            granted    = await self._auto_grant_locked_vc(member, after.channel)
            suppressed = bool(member.voice and member.voice.suppress)
            if suppressed:
                heal_task = asyncio.create_task(self._heal_suppress(member, after.channel))
                self._panel_tasks.add(heal_task)
                heal_task.add_done_callback(self._panel_tasks.discard)
            # One line per arrival so a reported voice drop can be matched to
            # what the bot did (or did not do) to that member.
            everyone_ow = after.channel.overwrites_for(guild.default_role)
            actions = [a for a, on in (("grant", granted), ("heal", suppressed)) if on]
            logger.info(
                "JTC move: member=%s from=%s to=%s locked=%s hidden=%s suppress=%s action=%s",
                member.id,
                before.channel.id if before.channel else None,
                after.channel.id,
                everyone_ow.connect is False,
                everyone_ow.view_channel is False,
                suppressed,
                "+".join(actions) or "none",
            )

        # Only on a real arrival in the trigger. Mute/deafen/stream toggles while
        # standing there used to spawn a second room and a second move.
        if (after.channel and jtc_id and after.channel.id == jtc_id
                and (before.channel is None or before.channel.id != jtc_id)
                and member.id not in self._creating):
            self._creating.add(member.id)
            try:
                cat = get(guild.categories, id=vc_cat_id) or after.channel.category
                await self._open_room(member, after.channel, cat)
            except Exception as e:
                logger.error("JTC: VC creation failed for %s: %s", member.display_name, e)
            finally:
                self._creating.discard(member.id)

        # Guest left an isolated room — revoke their overwrite so the room
        # disappears for them again. Creator, owners and the bot keep theirs.
        if (before.channel
                and before.channel.id in self.active_temp_vcs
                and (after.channel is None or after.channel.id != before.channel.id)
                and _is_isolated_creator(self.active_temp_vcs.get(before.channel.id))
                and member.id != self.active_temp_vcs.get(before.channel.id)
                and member.id not in MASTER_OWNERS
                and member.id != guild.me.id):
            await self._revoke_isolated_guest(member, before.channel)

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
                    if _is_new_room(vc):
                        continue  # mid-creation, not an orphan
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
                if _is_new_room(channel):
                    continue  # creator is still being moved in
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
