# PikalaxBOT - A Discord bot in discord.py
# Copyright (C) 2018  PikalaxALT
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import discord
from discord.ext import commands
from pikalaxbot.utils import friendly_date
import typing
import inspect
import os
import datetime

from . import BaseCog
from .utils.errors import *
from .utils.converters import CommandConverter


class Core(BaseCog):
    banlist = set()
    game = 'p!help'
    config_attrs = 'banlist', 'game'

    async def bot_check(self, ctx: commands.Context):
        if not self.bot.is_ready():
            raise NotReady('The bot is not ready to process commands')
        if not ctx.channel.permissions_for(ctx.me).send_messages:
            raise commands.BotMissingPermissions(['send_messages'])
        if isinstance(ctx.command, commands.Command) and await self.bot.is_owner(ctx.author):
            return True
        if ctx.author.id in self.banlist:
            raise BotIsIgnoringUser(f'I am ignoring {ctx.author}')
        return True

    @commands.command(aliases=['reboot'])
    @commands.is_owner()
    async def kill(self, ctx: commands.Context):
        """Shut down the bot (owner only, manual restart required)"""
        self.bot.reboot_after = ctx.invoked_with == 'reboot'
        await ctx.send('Rebooting to apply updates')
        await self.bot.logout()

    @commands.command()
    @commands.is_owner()
    async def ignore(self, ctx, person: discord.Member):
        """Ban a member :datsheffy:"""
        self.banlist.add(person.id)
        await ctx.send(f'{person.display_name} is now banned from interacting with me.')

    @commands.command()
    @commands.is_owner()
    async def unignore(self, ctx, person: discord.Member):
        """Unban a member"""
        self.banlist.discard(person.id)
        await ctx.send(f'{person.display_name} is no longer banned from interacting with me.')

    @commands.command()
    async def about(self, ctx):
        member: discord.Member = ctx.guild.me
        roles = [r.name.replace('@', '@\u200b') for r in member.roles]
        shared = sum(g.get_member(ctx.author.id) is not None for g in self.bot.guilds)
        e = discord.Embed()
        e.set_author(name=str(member))
        e.add_field(name='ID', value=member.id, inline=False)
        e.add_field(name='Guilds', value=f'{len(self.bot.guilds)} ({shared} shared)', inline=False)
        e.add_field(name='Joined', value=friendly_date.human_timedelta(member.joined_at), inline=False)
        e.add_field(name='Created', value=friendly_date.human_timedelta(member.created_at), inline=False)
        if roles:
            e.add_field(name='Roles', value=', '.join(roles) if len(roles) < 10 else f'{len(roles)} roles', inline=False)
        e.add_field(name='Source', value='https://github.com/PikalaxALT/pikalaxbot')
        e.add_field(name='Uptime', value=f'{datetime.datetime.utcnow() - self.bot._alive_since}')
        if member.colour.value:
            e.colour = member.colour
        if member.avatar:
            e.set_thumbnail(url=member.avatar_url)
        await ctx.send(embed=e)

    @commands.command()
    async def source(self, ctx, *, command: typing.Optional[CommandConverter]):
        """Links the source of the command. If command source cannot be retrieved,
        links the root of the bot's source tree."""
        url = 'https://github.com/PikalaxALT/pikalaxbot'
        if command is not None:
            src = command.callback.__code__.co_filename
            module = command.callback.__module__.replace('.', os.path.sep)
            if module in src:
                lines, start = inspect.getsourcelines(command.callback)
                sourcefile = src[src.index(module):].replace('\\', '/')
                end = start + len(lines) - 1
                url = f'{url}/blob/master/{sourcefile}#L{start}-L{end}'
        await ctx.send(f'<{url}>')

    @commands.Cog.listener()
    async def on_ready(self):
        self.bot._alive_since = self.bot._alive_since or datetime.datetime.utcnow()

    @commands.command()
    async def uptime(self, ctx):
        date = friendly_date.human_timedelta(self.bot._alive_since)
        await ctx.send(f'Bot last rebooted {date}')


def setup(bot):
    bot.add_cog(Core(bot))
