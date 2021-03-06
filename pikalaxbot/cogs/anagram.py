# PikalaxBOT - A Discord bot in discord.py
# Copyright (C) 2018-2021  PikalaxALT
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

from discord.ext import commands

from . import *
from .utils.game import GameBase, GameCogBase, GameStartCommand
from ..pokeapi import methods


class AnagramGame(GameBase):
    def __init__(self, bot, attempts=3):
        super().__init__(bot)
        self._attempts = attempts
        self._state = ''
        self._solution_name = ''
        self._incorrect: list[str] = []
        self.attempts = 0

    def reset(self):
        super().reset()
        self._state = ''
        self._solution = None
        self._solution_name = ''
        self._incorrect = []
        self.attempts = 0

    @property
    def incorrect(self):
        return ', '.join(self._incorrect)

    def __str__(self):
        return f'```Puzzle: {self.state}\n' \
               f'Incorrect: [{self.incorrect}]\n' \
               f'Remaining: {self.attempts:d}```'

    async def start(self, ctx):
        if self.running:
            await ctx.send(f'{ctx.author.mention}: Anagram is already running here.',
                           delete_after=10)
        else:
            self._solution = await methods.random_pokemon()
            self._solution_name = methods.get_name(self._solution, clean=True).upper()
            _state = list(self._solution_name)
            while ''.join(_state) == self._solution_name:
                random.shuffle(_state)
            self._state = ''.join(_state)
            self.attempts = self._attempts
            self._incorrect.clear()
            await ctx.send(f'Anagram has started! You have {self.attempts:d} attempts and {self._timeout:d} seconds '
                           f'to guess correctly before OLDEN corrupts your save.\n')
            await super().start(ctx)

    async def end(self, ctx, failed=False, aborted=False):
        if await super().end(ctx, failed=failed, aborted=aborted):
            await self._message.edit(content=self)
            embed = await self.get_solution_embed(failed=failed, aborted=aborted)
            if aborted:
                await ctx.send(f'Game terminated by {ctx.author.mention}.\n'
                               f'Solution: {self._solution_name}',
                               embed=embed)
            elif failed:
                await ctx.send(f'You were too late, welcome to Glitch Purgatory.\n'
                               f'Solution: {self._solution_name}',
                               embed=embed)
            else:
                self.add_player(ctx.author)
                score = await self.award_points()
                await ctx.send(f'{ctx.author.mention} has solved the puzzle!\n'
                               f'Solution: {self._solution_name}\n'
                               f'{ctx.author.mention} earned {score} points for winning!',
                               embed=embed)
            self.reset()
        else:
            await ctx.send(f'{ctx.author.mention}: Anagram is not running here. '
                           f'Start a game by saying `{ctx.prefix}anagram start`.',
                           delete_after=10)

    async def solve(self, ctx: MyContext, guess: str):
        if self.running:
            guess = guess.upper()
            if guess in self._incorrect:
                await ctx.send(f'{ctx.author.mention}: Solution already guessed: {guess}',
                               delete_after=10)
            else:
                if self._solution_name == guess:
                    self._state = self._solution_name
                    await self.end(ctx)
                else:
                    self._incorrect.append(guess)
                    self.attempts -= 1
            if self.running:
                await self._message.edit(content=self)
                if self.attempts == 0:
                    await self.end(ctx, True)
        else:
            await ctx.send(f'{ctx.author.mention}: Anagram is not running here. '
                           f'Start a game by saying `{ctx.prefix}anagram start`.',
                           delete_after=10)

    async def show(self, ctx):
        if await super().show(ctx) is None:
            await ctx.send(f'{ctx.author.mention}: Anagram is not running here. '
                           f'Start a game by saying `{ctx.prefix}anagram start`.',
                           delete_after=10)


class Anagram(GameCogBase[AnagramGame]):
    """Play a Pokemon anagram game.

    All commands are under the `anagram` group,
    or you can use one of the shortcuts."""

    def cog_check(self, ctx: MyContext):
        return self._local_check(ctx) and ctx.bot.pokeapi is not None

    @commands.group(case_insensitive=True, invoke_without_command=True)
    async def anagram(self, ctx: MyContext):
        """Play Anagram"""
        await ctx.send_help(ctx.command)

    @anagram.command(cls=GameStartCommand)
    async def start(self, ctx: MyContext):
        """Start a game in the current channel"""
        await self.game_cmd('start', ctx)

    @commands.command(name='anastart', aliases=['ast'], cls=GameStartCommand)
    async def anagram_start(self, ctx: MyContext):
        """Start a game in the current channel"""
        await self.start(ctx)

    @anagram.command()
    async def solve(self, ctx: MyContext, *, guess: str):
        """Make a guess, if you dare"""
        await self.game_cmd('solve', ctx, guess)

    @commands.command(name='anasolve', aliases=['aso'])
    async def anagram_solve(self, ctx: MyContext, *, guess: str):
        """Make a guess, if you dare"""
        await self.solve(ctx, guess=guess)

    @anagram.command()
    @commands.is_owner()
    async def end(self, ctx: MyContext):
        """End the game as a loss (owner only)"""
        await self.game_cmd('end', ctx, aborted=True)

    @commands.command(name='anaend', aliases=['ae'])
    @commands.is_owner()
    async def anagram_end(self, ctx: MyContext):
        """End the game as a loss (owner only)"""
        await self.end(ctx)

    @anagram.command()
    async def show(self, ctx: MyContext):
        """Show the board in a new message"""
        await self.game_cmd('show', ctx)

    @commands.command(name='anashow', aliases=['ash'])
    async def anagram_show(self, ctx: MyContext):
        """Show the board in a new message"""
        await self.show(ctx)

    async def cog_command_error(self, ctx: MyContext, exc: commands.CommandError):
        await self._error(ctx, exc)
