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

import asyncio
import discord
import math
import time
from .. import BaseCog
from discord.ext import commands
from .errors import BadGameArgument
import typing
if typing.TYPE_CHECKING:
    from ...ext.pokeapi import PokeApi
    from ... import MyContext

__all__ = (
    'find_emoji',
    'increment_score',
    'GameBase',
    'GameStartCommand',
    'GameCogBase',
)


def find_emoji(guild, name, case_sensitive=True):
    def lower(s):
        return s if case_sensitive else s.lower()

    return discord.utils.find(lambda e: lower(name) == lower(e.name), guild.emojis)


async def increment_score(sql, player, *, by=1):
    await sql.execute(
        'insert into game '
        'values ($1, $2, $3) '
        'on conflict(id) '
        'do update '
        'set score = game.score + $3',
        player.id, player.name, by)


class NoInvokeOnEdit(commands.CheckFailure):
    pass


class GameBase:
    __slots__ = (
        'bot', '_timeout', '_lock', '_max_score', '_state', '_running', '_message', '_task',
        'start_time', '_players', '_solution'
    )

    def __init__(self, bot, timeout=90, max_score=1000):
        self.bot = bot
        self._timeout = timeout
        self._lock = asyncio.Lock()
        self._max_score = max_score
        self.reset()

    async def __aenter__(self):
        await self._lock.acquire()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self._lock.release()

    def reset(self):
        self._state = None
        self._running = False
        self._message = None
        self._task = None
        self.start_time = -1
        self._players = set()
        self._solution: typing.Optional['PokeApi.PokemonSpecies'] = None

    @property
    def state(self):
        return self._state

    @property
    def score(self):
        end_time = time.time()
        if self._timeout is None:
            time_factor = 2 ** ((self.start_time - end_time) / 300.0)
        else:
            time_factor = (self._timeout - end_time + self.start_time) / self._timeout
        return max(int(math.ceil(self._max_score * time_factor)), 1)

    @property
    def running(self):
        return self._running

    @running.setter
    def running(self, state):
        self._running = state

    def __str__(self):
        pass

    def add_player(self, player):
        self._players.add(player)

    def get_player_names(self):
        return ', '.join(player.name for player in self._players)

    async def timeout(self, ctx):
        await asyncio.sleep(self._timeout)
        if self.running:
            await ctx.send('Time\'s up!')
            self.bot.loop.create_task(self.end(ctx, failed=True))

    async def start(self, ctx):
        def destroy_self(task):
            self._task = None

        self.running = True
        self._message = await ctx.send(self)
        if self._timeout is None:
            self._task = self.bot.loop.create_future()
        else:
            self._task = self.bot.loop.create_task(self.timeout(ctx))
        self._task.add_done_callback(destroy_self)
        self.start_time = ctx.message.created_at.timestamp()

    async def end(self, ctx, failed=False, aborted=False):
        if self.running:
            if self._task and not self._task.done():
                self._task.cancel()
            return True
        return False

    async def show(self, ctx):
        if self.running:
            await self._message.delete()
            self._message = await ctx.send(self)
            return self._message
        return None

    async def award_points(self):
        score = max(math.ceil(self.score / len(self._players)), 1)
        async with self.bot.sql as sql:
            for player in self._players:
                await increment_score(sql, player, by=score)
        return score

    async def get_solution_embed(self, *, failed=False, aborted=False):
        sprite_url = await self.bot.pokeapi.get_species_sprite_url(self._solution)
        return discord.Embed(
                title=self._solution.name,
                colour=discord.Colour.red() if failed or aborted else discord.Colour.green()
            ).set_image(url=sprite_url or discord.Embed.Empty)


class GameStartCommand(commands.Command):
    @property
    def _max_concurrency(self):
        if self.cog:
            return self.cog._max_concurrency

    @_max_concurrency.setter  # Workaround for super __init__
    def _max_concurrency(self, value):
        pass


class GameCogBase(BaseCog):
    gamecls = None

    async def init_db(self, sql):
        await sql.execute("create table if not exists game (id bigint unique primary key, name varchar(32), score integer default 0)")

    def _local_check(self, ctx: 'MyContext'):
        if ctx.guild is None:
            raise commands.NoPrivateMessage('This command cannot be used in private messages.')
        if ctx.message.edited_at:
            raise NoInvokeOnEdit('This command cannot be invoked by editing your message')
        return True

    def __init__(self, bot):
        if self.gamecls is None:
            raise NotImplemented('this class must be subclassed')
        super().__init__(bot)
        self.channels = {}
        self._max_concurrency = commands.MaxConcurrency(1, per=commands.BucketType.channel, wait=False)

    def __getitem__(self, channel):
        if channel not in self.channels:
            self.channels[channel] = self.gamecls(self.bot)
        return self.channels[channel]

    async def game_cmd(self, cmd, ctx, *args, **kwargs):
        async with self[ctx.channel.id] as game:
            cb = getattr(game, cmd)
            if cb is None:
                await ctx.send(f'{ctx.author.mention}: Invalid command: '
                               f'{ctx.prefix}{self.gamecls.__class__.__name__.lower()} {cmd}',
                               delete_after=10)
            else:
                await cb(ctx, *args, **kwargs)
        if cmd == 'start':
            await asyncio.wait({
                ctx._task,
                asyncio.wait_for(self[ctx.channel.id]._task, None)
            }, return_when=asyncio.FIRST_COMPLETED)

    async def _error(self, ctx, exc):
        if isinstance(exc, BadGameArgument):
            await ctx.send(f'{ctx.author.mention}: Invalid arguments. '
                           f'Try using two numbers (i.e. 2 5) or a letter '
                           f'and a number (i.e. c2).',
                           delete_after=10)
        elif isinstance(exc, (commands.NoPrivateMessage, NoInvokeOnEdit)):
            await ctx.send(exc)
        elif isinstance(exc, commands.MaxConcurrencyReached):
            await ctx.send(f'{self.qualified_name} is already running here')
        else:
            await self.bot.send_tb(ctx, exc, origin=f'command {ctx.command}')
        self.log_tb(ctx, exc)

    async def end_quietly(self, ctx, history):
        async with self[ctx.channel.id] as game:
            if game.running and game._message and game._message.id in history:
                game._task.cancel()
                game.reset()
