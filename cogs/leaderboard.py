import asyncio
import discord
from discord.ext import commands
from utils import sql
from bot import PikalaxBOT


class Leaderboard:
    def __init__(self, bot):
        self.bot = bot  # type: PikalaxBOT

    @commands.group(pass_context=True)
    async def leaderboard(self, ctx):
        pass

    @leaderboard.command()
    async def check(self, ctx, username=None):
        if username is None:
            person = ctx.author
        else:
            for person in self.bot.get_all_members():
                if username in (person.name, person.mention, person.display_name):
                    break
            else:
                await ctx.send(f'{ctx.author.mention}: User {username} not found.')
                return  # bail early
        score = sql.get_score(person)
        if score is not None:
            await ctx.send(f'{person.mention} has {score:d} point(s) across all games.')
        else:
            await ctx.send(f'{person.mention} is not yet on the leaderboard.')

    @leaderboard.command()
    async def show(self, ctx):
        msgs = []
        for _id, name, score in sql.get_all_scores():
            msgs.append(f'{name}: {score:d}')
        if len(msgs) == 0:
            await ctx.send('The leaderboard is empty. Play some games to get your name up there!')
        else:
            msg = '\n'.join(msgs)
            await ctx.send(f'Leaderboard:\n'
                           f'```\n'
                           f'{msg}\n'
                           f'```')


def setup(bot):
    bot.add_cog(Leaderboard(bot))
