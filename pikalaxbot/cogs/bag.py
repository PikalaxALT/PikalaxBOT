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

from discord.ext import commands
from . import BaseCog
from .utils.game import find_emoji
import aiosqlite


class Bag(BaseCog):
    """Commands related to Lillie's bag. Get in, Nebby."""

    default_bag = (
        ('happily jumped into the bag!',),
        ('reluctantly clambored into the bag.',),
        ('turned away!',),
        ('let out a cry in protest!',)
    )

    async def init_db(self, sql):
        await sql.execute("create table if not exists meme (bag text unique)")
        await sql.executemany("insert into meme values (?) on conflict (bag) do nothing", self.default_bag)

    @commands.group(invoke_without_command=True)
    async def bag(self, ctx):
        """Get in the bag, Nebby."""
        async with self.bot.sql as sql:
            async for message, in sql.execute('select bag from meme order by random() limit 1'):
                await ctx.send(f'*{message}*')
                break
            else:
                emoji = find_emoji(ctx.bot, 'BibleThump', case_sensitive=False)
                await ctx.send(f'*cannot find the bag {emoji}*')

    @bag.command()
    async def add(self, ctx, *, fmtstr):
        """Add a message to the bag."""
        try:
            async with self.bot.sql as sql:
                await sql.execute('insert into meme values (?)', (fmtstr,))
        except aiosqlite.Error:
            await ctx.send('That message is already in the bag')
        else:
            await ctx.send('Message was successfully placed in the bag')

    @bag.command(name='remove')
    @commands.is_owner()
    async def remove_bag(self, ctx, *, msg):
        """Remove a phrase from the bag"""
        if msg in self.default_bag:
            return await ctx.send('Cannot remove default message from bag')
        try:
            async with self.bot.sql as sql:
                await sql.execute('delete from meme where bag = ?', (msg,))
        except aiosqlite.Error:
            await ctx.send('Cannot remove message from the bag')
        else:
            await ctx.send('Removed message from bag')

    @bag.command(name='reset')
    @commands.is_owner()
    async def reset_bag(self, ctx):
        """Reset the bag"""
        async with self.bot.sql as sql:
            await sql.execute('drop table meme')
            await self.init_db(sql)
        await ctx.send('Reset the bag')


def setup(bot):
    bot.add_cog(Bag(bot))
