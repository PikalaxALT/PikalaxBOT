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

import random
import aiohttp
import typing
import platform
import datetime
import os

import discord
from discord.ext import commands

from . import BaseCog
from .utils.data import data

__dir__ = os.path.dirname(os.path.dirname(__file__)) or '.'
with open(os.path.join(os.path.dirname(__dir__), 'version.txt')) as fp:
    __version__ = fp.read().strip()


class HMM:
    def __init__(self, transition, emission):
        self.transition = transition
        self.emission = emission
        self.state = 0

    @property
    def n_states(self):
        return len(self.transition)

    def emit(self):
        res = self.emission[self.state]
        self.state, = random.choices(range(self.n_states), weights=self.transition[self.state])
        return res

    def get_chain(self, length, start=0, end=-1):
        self.state = start
        for i in range(length):
            yield self.emit()
            if self.state == end:
                break


class Meme(BaseCog):
    _nebby = HMM(
        [[0, 1, 0, 0, 0],
         [1, 2, 1, 0, 0],
         [0, 0, 1, 1, 0],
         [0, 0, 0, 1, 9],
         [0, 0, 0, 0, 1]],
        'pew! '
    )

    def __init__(self, bot):
        super().__init__(bot)
        self.session: typing.Optional[aiohttp.ClientSession] = None

        async def create_session():
            self.session = aiohttp.ClientSession(raise_for_status=True)

        bot.loop.create_task(create_session())

    def cog_unload(self):
        self.bot.loop.create_task(self.session.close())

    async def init_db(self, sql):
        c = await sql.execute("select count(*) from sqlite_master where type='table' and name='meme'")
        exists, = await c.fetchone()
        await sql.execute("create table if not exists meme (bag text primary key)")
        if not exists:
            await sql.executemany("insert into meme(bag) values (?)", sql.default_bag)

    async def cog_command_error(self, ctx, error):
        await ctx.send(f'**{error.__class__.__name__}:** {error}')

    @commands.command()
    async def archeops(self, ctx, *subjs):
        """Generates a random paragraph using <arg1> and <arg2> as subject keywords, using the WatchOut4Snakes frontend.
        """
        if len(subjs) > 2:
            raise commands.BadArgument('maximum two subjects for archeops command')
        timeout = aiohttp.ClientTimeout(total=15.0)
        params = {f'Subject{i + 1}': (f'BLAH{i + 1}' if i < len(subjs) else '') for i in range(2)}
        async with ctx.typing():
            async with self.session.post('http://www.watchout4snakes.com/wo4snakes/Random/RandomParagraph', data=params, timeout=timeout) as r:
                res = await r.text()
        for i, subj in enumerate(subjs):
            res = res.replace(f'BLAH{i + 1}', subj)
        await ctx.send(res)

    @commands.command()
    async def riot(self, ctx, *, args):
        """Riots (for some reason)"""
        resp = args.upper()
        if 'DANCE' in resp:
            await ctx.send(f'♫ ┌༼ຈل͜ຈ༽┘ ♪ {resp} RIOT ♪ └༼ຈل͜ຈ༽┐♫')
        else:
            await ctx.send(f'ヽ༼ຈل͜ຈ༽ﾉ {resp} RIOT ヽ༼ຈل͜ຈ༽ﾉ')

    @commands.command()
    async def nebby(self, ctx):
        """Pew!"""
        emission = ''.join(self._nebby.get_chain(100, end=4)).title()
        await ctx.send(emission)

    @commands.command()
    async def yolonome(self, ctx):
        """Happy birthday, Waggle!"""
        await ctx.send(f'{ctx.author.mention} used Metronome!\n'
                       f'Waggling a finger allowed it to use {data.random_move_name()}!')

    @commands.command()
    async def olden(self, ctx):
        await ctx.send('https://vignette.wikia.nocookie.net/twitchplayspokemoncrystal/images/5/5f/'
                       'Serious_%22OLDEN%22_Times.png/revision/latest?cb=20160820193335')

    @commands.command()
    async def honk(self, ctx):
        emoji = discord.utils.get(self.bot.emojis, name='HONK')
        await ctx.message.add_reaction(emoji)

    @commands.guild_only()
    @commands.command()
    async def someone(self, ctx):
        await ctx.send(random.choice(ctx.guild.members).mention, allowed_mentions=discord.AllowedMentions.none())

    @commands.command()
    async def beans(self, ctx):
        for attempt in range(10):
            async with self.session.get('https://reddit.com/r/beans/random.json', headers={'user-agent': f'{platform.platform()}:{self.bot.user.name}:{__version__}'}) as r:
                resp = await r.json()
            child = resp[0]['data']['children'][0]['data']
            if child.get('url') and not child.get('is_video'):
                break
        else:
            return await ctx.send('Hmm... I seem to be out of beans right now')
        author = child['author']
        permalink = child['permalink']
        embed = discord.Embed(title=child['title'], url=f'https://reddit.com{permalink}', colour=discord.Colour.dark_orange(), timestamp=datetime.datetime.fromtimestamp(child['created_utc']))
        embed.set_image(url=child['url'])
        embed.set_author(name=f'/u/{author}', url=f'https://reddit.com/u/{author}')
        await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(Meme(bot))
