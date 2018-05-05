import asyncio
import discord
import random
from utils.data import data
from discord.ext import commands


class HangmanGame:
    def __init__(self, bot, attempts=8):
        self.bot = bot
        self._attempts = attempts
        self.reset()

    def reset(self):
        self._running = False
        self._state = []
        self._solution = ''
        self._incorrect = []
        self.attempts = 0

    @property
    def state(self):
        return ' '.join(self._state)

    @property
    def incorrect(self):
        return ', '.join(self._incorrect)

    @property
    def running(self):
        return self._running

    @running.setter
    def running(self, state):
        self._running = state

    async def start(self, ctx):
        if self.running:
            await self.bot.say(f'{ctx.author.mention}: Hangman is already running here.')
        else:
            self._solution = random.choice(data.pokemon)
            self._state = ['_' for c in self._solution]
            self.attempts = self._attempts
            self._incorrect = []
            self.running = True
            await self.bot.say(f'Hangman has started! You have {self.attempts:d} attempts to guess correctly before '
                               f'the man dies!\n'
                               f'Puzzle: {self.state} | Incorrect: [{self.incorrect}]')

    async def end(self, ctx, failed=False):
        if failed:
            await ctx.send(f'You were too late, the man has hanged to death.\n'
                           f'Solution: {self._solution}')
        else:
            await ctx.send(f'{ctx.author.mention} has solved the puzzle!\n'
                           f'Solution: {self._solution}')
        self.reset()

    async def guess(self, ctx, guess):
        guess = guess.upper()
        if guess in self._incorrect or guess in self._state:
            await ctx.send(f'Character or solution already guessed: {guess}')
        elif len(guess) == 1:
            found = False
            for i, c in enumerate(self._solution):
                if c == guess:
                    self._state[i] = guess
                    found = True
            if found:
                if ''.join(self._state) == self._solution:
                    await self.end(ctx)
            else:
                self._incorrect.append(guess)
                self.attempts -= 1
        else:
            if self._solution == guess:
                self._state = list(self._solution)
                await self.end(ctx)
            else:
                self._incorrect.append(guess)
                self.attempts -= 1
        if self.running:
            await ctx.send(f'Puzzle: {self.state} | Incorrect: [{self.incorrect}]')
            if self.attempts == 0:
                await self.end(ctx, True)


class Hangman:
    def __init__(self, bot, attempts=8):
        self.bot = bot
        self._attempts = attempts
        self.channels = []

    @commands.group(pass_context=True)
    async def hangman(self, ctx):
        if ctx.channel not in self.channels:
            self.channels.append(HangmanGame(self.bot, self._attempts))
            if ctx.invoked_subcommand is None:
                await ctx.send(f'Incorrect hangman subcommand passed. Try {ctx.prefix}help hangman')

    @hangman.command()
    async def start(self, ctx):
        await self.channels[ctx.channel].start(ctx)

    @hangman.command()
    async def guess(self, ctx, guess):
        await self.channels[ctx.channel].guess(ctx, guess)

    @hangman.command()
    async def end(self, ctx):
        await self.channels[ctx.channel].end(ctx, True)


def setup(bot):
    bot.add_cog(Hangman(bot))
