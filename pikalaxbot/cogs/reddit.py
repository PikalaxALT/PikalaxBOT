import aiohttp
import platform
import datetime

import discord
from discord.ext import commands

from . import BaseCog

from .. import __version__


class NoPostsFound(commands.CommandError):
    def __init__(self, subreddit, message=None, *args):
        super().__init__(message=message, *args)
        self.subreddit = subreddit


class Reddit(BaseCog):
    """Commands for yoinking image posts off of Reddit."""

    def __init__(self, bot):
        super().__init__(bot)
        self.session: aiohttp.ClientSession = bot.client_session
        self.headers = {'user-agent': f'{platform.platform()}:{self.bot.user.name}:{__version__} (by /u/pikalaxalt)'}

    async def get_reddit(self, endpoint):
        async with self.session.get(f'https://reddit.com/{endpoint}', headers=self.headers) as r:
            resp = await r.json()
            if isinstance(resp, dict):
                raise aiohttp.ClientResponseError(
                    status=404,
                    message=f'Unable to reach {endpoint}',
                    history=(r,),
                    request_info=r.request_info
                )
        return resp

    async def fetch_subreddit_info(self, subreddit):
        resp = await self.get_reddit(f'r/{subreddit}/about.json')
        return resp['data']

    async def fetch_random_reddit_post(self, subreddit):
        resp = await self.get_reddit(f'r/{subreddit}/random.json')
        return resp[0]['data']['children'][0]['data']

    def cog_check(self, ctx):
        return ctx.guild.id not in self.bot.settings.banned_guilds

    async def get_subreddit_embed(self, ctx, subreddit):
        min_creation = ctx.message.created_at - datetime.timedelta(hours=3)

        subinfo = await self.fetch_subreddit_info(subreddit)
        if subinfo['over18'] and not ctx.channel.is_nsfw():
            raise commands.NSFWChannelRequired

        def check(post):
            return (post['approved_at_utc'] or datetime.datetime.fromtimestamp(post['created_utc']) <= min_creation) \
                and post['score'] >= 10 \
                and (not post['over_18'] or ctx.channel.is_nsfw()) \
                and not post['spoiler']

        for attempt in range(10):
            child = await self.fetch_random_reddit_post(subreddit)
            if not check(child):
                continue
            if child.get('url_overridden_by_dest') and not child.get('is_video') and not child.get('media'):
                break
        else:
            raise NoPostsFound(subreddit)
        title = child['title']
        sub_prefixed = child['subreddit_name_prefixed']
        author = child['author']
        permalink = child['permalink']
        score = child['score']
        upvote_emoji = discord.utils.get(self.bot.emojis, name='upvote')
        embed = discord.Embed(
            title=f'/{sub_prefixed}',
            description=f'[{title}](https://reddit.com{permalink})\n'
                        f'Score: {score}{upvote_emoji}',
            url=f'https://reddit.com/{sub_prefixed}',
            colour=discord.Colour.dark_orange(),
            timestamp=datetime.datetime.fromtimestamp(child['created_utc'])
        )
        embed.set_image(url=child['url'])
        embed.set_author(name=f'/u/{author}', url=f'https://reddit.com/u/{author}')
        return embed

    @commands.command(name='reddit', aliases=['sub'])
    async def get_subreddit(self, ctx, subreddit):
        """Randomly fetch an image post from the given subreddit."""
        async with ctx.typing():
            embed = await self.get_subreddit_embed(ctx, subreddit)
        await ctx.send(embed=embed)

    @commands.command()
    async def beans(self, ctx):
        """Gimme my beans reeeeeeeeeeeeee"""
        await self.get_subreddit(ctx, 'beans')

    async def cog_command_error(self, ctx, error):
        error = getattr(error, 'original', error)
        if isinstance(error, aiohttp.ClientResponseError):
            if error.status == 404:
                await ctx.send('I cannot find that subreddit!')
            else:
                await ctx.send(f'An unhandled HTTP exception occurred: {error.status}: {error.message}')
        elif isinstance(error, NoPostsFound):
            await ctx.send(f'Hmm... I seem to be out of {error.subreddit} right now')
        elif isinstance(error, commands.NSFWChannelRequired):
            await ctx.send('That subreddit is too spicy for this channel!')
        elif isinstance(error, commands.CheckFailure):
            pass
        else:
            await ctx.send(f'An unhandled internal exception occurred: {error.__class__.__name__}: {error}')


def setup(bot):
    bot.add_cog(Reddit(bot))
