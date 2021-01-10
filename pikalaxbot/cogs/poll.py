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
from discord.ext import commands, tasks
from . import *
import datetime
import typing
import base64
import math
import aioitertools
import asyncpg
import operator
import textwrap
from collections import Counter

from .utils.errors import *
from .utils.converters import FutureTime


class BadPollTimeArgument(commands.BadArgument):
    pass


class PollTime(FutureTime, float):
    @classmethod
    async def convert(cls, ctx, argument):
        try:
            value = await FutureTime.convert(ctx, argument)
        except commands.ConversionError:
            value = float(argument)
        else:
            value = (value.dt - ctx.message.created_at).total_seconds()
        if value <= 0 or not math.isfinite(value):
            raise BadPollTimeArgument
        return value


class PollManager:
    __slots__ = (
        'bot',
        'channel_id',
        'context_id',
        'message',
        'owner_id',
        'options',
        'votes',
        '_hash',
        '_message_id',
        'start_time',
        'stop_time',
        'emojis',
        'task',
        'unloading'
    )

    def __init__(
            self,
            *,
            bot: PikalaxBOT,
            channel_id: int,
            context_id: int,
            owner_id: int,
            start_time: datetime.datetime,
            stop_time: datetime.datetime,
            my_hash: typing.Optional[str] = None,
            votes: typing.Optional[dict[int, int]] = None,
            options: typing.Optional[typing.Sequence[str]] = None
    ):
        self.bot = bot
        self.channel_id = channel_id
        self.context_id = context_id
        self.owner_id = owner_id
        self.start_time = start_time
        self.stop_time = stop_time
        if my_hash:
            assert self.hash == my_hash
        self.votes: dict[int, int] = votes or {}
        self.options: list[str] = options or []
        self.emojis = [f'{i + 1}\u20e3' if i < 9 else '\U0001f51f' for i in range(len(options))]
        self.task: typing.Optional[asyncio.Task] = None
        self.unloading = False
        self.message: typing.Union[discord.Message, discord.PartialMessage, None] = None

    @discord.utils.cached_slot_property('_hash')
    def hash(self):
        return base64.b32encode((hash(self) & 0xFFFFFFFF).to_bytes(4, 'little')).decode().rstrip('=')

    def __iter__(self):
        yield self.hash
        yield self.channel_id
        yield self.owner_id
        yield self.context_id
        yield self.message_id
        yield self.start_time
        yield self.stop_time

    @classmethod
    async def from_command(cls, context: MyContext, timeout: float, prompt: str, *options: str):
        this = cls(
            bot=context.bot,
            channel_id=context.channel.id,
            context_id=context.message.id,
            owner_id=context.author.id,
            start_time=context.message.created_at,
            stop_time=context.message.created_at + datetime.timedelta(seconds=timeout),
            options=options
        )
        content = f'Vote using emoji reactions. ' \
                  f'Max one vote per user. ' \
                  f'To change your vote, clear your original selection first. ' \
                  f'The poll author may not cast a vote. ' \
                  f'The poll author may cancel the poll using ' \
                  f'`{context.prefix}{context.cog.cancel.qualified_name} {this.hash}` ' \
                  f'or by deleting this message.'
        description = '\n'.join(map('{0}: {1}'.format, this.emojis, options))
        embed = discord.Embed(title=prompt, description=description, colour=0xf47fff)
        embed.set_footer(text='Poll ends at')
        embed.timestamp = this.stop_time
        embed.set_author(name=context.author.display_name, icon_url=context.author.avatar_url)
        this.message = await context.send(content, embed=embed)
        for emoji in this.emojis:
            await this.message.add_reaction(emoji)
        return this

    @classmethod
    async def from_sql(
            cls,
            bot: PikalaxBOT,
            sql: asyncpg.Connection,
            my_hash: str,
            channel_id: int,
            owner_id: int,
            context_id: int,
            message_id: int,
            start_time: datetime.datetime,
            stop_time: datetime.datetime
    ):
        message: discord.PartialMessage = bot.get_channel(channel_id).get_partial_message(message_id)
        this = cls(
            bot=bot,
            channel_id=channel_id,
            context_id=context_id,
            owner_id=owner_id,
            start_time=start_time,
            stop_time=stop_time,
            my_hash=my_hash,
            votes=dict(await sql.fetch('select voter, option from poll_options where code = $1', my_hash)),
            options=[option.split(' ', 1)[1] for option in message.embeds[0].description.splitlines()]
        )
        this.message = message
        return this

    @discord.utils.cached_slot_property('_message_id')
    def message_id(self):
        if self.message:
            return self.message.id

    def __eq__(self, other):
        if isinstance(other, PollManager):
            return hash(self) == hash(other)
        if isinstance(other, str):
            return self.hash == other
        raise NotImplementedError

    def __repr__(self):
        return f'<{self.__class__.__name__} object with code {self.hash} and {len(self.options)} options>'

    def __ne__(self, other):
        return not self.__eq__(other)

    def __hash__(self):
        return hash((self.start_time.timestamp(), self.stop_time.timestamp(), self.channel_id, self.owner_id))

    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if payload.message_id != self.message_id:
            return
        if payload.emoji.name not in self.emojis:
            return
        if payload.user_id in {self.owner_id, self.bot.user.id}:
            return
        if payload.user_id in self.votes:
            return
        selection = self.emojis.index(payload.emoji.name)
        self.votes[payload.user_id] = selection
        async with self.bot.sql as sql:  # type: asyncpg.Connection
            await sql.execute(
                'insert into poll_options (code, voter, option)'
                ' values ($1, $2, $3)',
                self.hash, payload.user_id, selection
            )

    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        if payload.message_id != self.message_id:
            return
        if payload.emoji.name not in self.emojis:
            return
        if payload.user_id in {self.owner_id, self.bot.user.id}:
            return
        selection = self.emojis.index(payload.emoji.name)
        if self.votes.get(payload.user_id) != selection:
            return
        self.votes.pop(payload.user_id)
        async with self.bot.sql as sql:  # type: asyncpg.Connection
            await sql.execute('delete from poll_options where code = $1 and voter = $2', self.hash, payload.user_id)

    async def on_raw_message_delete(self, payload: discord.RawMessageDeleteEvent):
        if payload.message_id == self.message_id:
            self.message = None
            self.cancel()

    def start(self):
        self.unloading = False
        now = datetime.datetime.utcnow()
        if now > self.stop_time:
            self.bot.dispatch('poll_end', self)
            return
        self.bot.add_listener(self.on_raw_reaction_add)
        self.bot.add_listener(self.on_raw_reaction_remove)
        self.bot.add_listener(self.on_raw_message_delete)

        async def run():
            try:
                await asyncio.sleep((self.stop_time - datetime.datetime.utcnow()).total_seconds())
            finally:
                self.bot.remove_listener(self.on_raw_reaction_add)
                self.bot.remove_listener(self.on_raw_reaction_remove)
                self.bot.remove_listener(self.on_raw_message_delete)
                if not self.unloading:
                    self.bot.dispatch('poll_end', self)

        self.task = asyncio.create_task(run())

    def cancel(self, unloading=False):
        self.unloading = unloading
        self.task.cancel()

    @classmethod
    async def convert(cls, ctx: MyContext, argument: str):
        mgr: typing.Optional['PollManager'] = discord.utils.get(ctx.cog.polls, hash=argument)
        if mgr is None:
            raise NoPollFound('The supplied code does not correspond to a running poll')
        return mgr


class Poll(BaseCog):
    """Commands for starting and managing opinion polls"""

    TIMEOUT = 60

    def __init__(self, bot):
        super().__init__(bot)
        self.polls: list[PollManager] = []

    def cog_unload(self):
        self.cleanup_polls.cancel()
        for mgr in self.polls:
            mgr.cancel(True)

    async def init_db(self, sql):
        await sql.execute(
            'create table if not exists polls ('
            'code varchar(8) unique primary key, '
            'channel bigint, '
            'owner bigint, '
            'context bigint, '
            'message bigint, '
            'started timestamp, '
            'closes timestamp'
            ')'
        )
        await sql.execute(
            'create table if not exists poll_options ('
            'code varchar(8) references polls(code), '
            'voter bigint, '
            'option integer'
            ')'
        )
        self.cleanup_polls.start()

    @tasks.loop(seconds=60)
    async def cleanup_polls(self):
        self.polls = [poll for poll in self.polls if not poll.task or not poll.task.done()]

    @cleanup_polls.error
    async def cleanup_polls_error(self, error: BaseException):
        await self.bot.send_tb(None, error, origin='Poll.cleanup_polls')

    @cleanup_polls.before_loop
    async def cache_polls(self):
        await self.bot.wait_until_ready()
        try:
            async with self.bot.sql as sql:  # type: asyncpg.Connection
                for row in await sql.fetch('select * from polls'):
                    try:
                        mgr = await PollManager.from_sql(self.bot, sql, *row)
                        self.polls.append(mgr)
                        mgr.start()
                    except discord.HTTPException:
                        pass
        except Exception as e:
            await self.bot.send_tb(None, e, origin='Poll.cache_polls')

    @commands.group(name='poll', invoke_without_command=True)
    async def poll_cmd(self, ctx: MyContext, timeout: typing.Optional[PollTime], prompt, *opts):
        """Create a poll with up to 10 options.  Poll will last for 60.0 seconds (or as specified),
        with sudden death tiebreakers as needed.  Use quotes to enclose multi-word
duration, prompt, and options."""

        timeout = timeout or Poll.TIMEOUT
        # Do it this way because `set` does weird things with ordering
        options = []
        for opt in opts:
            if opt not in options:
                options.append(opt)
        nopts = len(options)
        if nopts > 10:
            raise TooManyOptions('Too many options!')
        if nopts < 2:
            raise NotEnoughOptions('Not enough unique options!')
        mgr = await PollManager.from_command(ctx, timeout, prompt, *options)
        async with ctx.bot.sql as sql:  # type: asyncpg.Connection
            await sql.execute(
                'insert into polls (code, channel, owner, context, message, started, closes) '
                'values ($1, $2, $3, $4, $5, $6, $7)',
                *mgr
            )
        self.polls.append(mgr)
        mgr.start()

    @commands.max_concurrency(1, commands.BucketType.channel)
    @poll_cmd.command(name='new')
    async def interactive_poll_maker(self, ctx: MyContext, timeout: PollTime = TIMEOUT):
        """Create a poll interactively"""

        embed = discord.Embed(
            title='Interactive Poll Maker',
            description=f'Poll created by {ctx.author.mention}\n\n'
                        f'React with :x: to cancel.',
            colour=discord.Colour.orange()
        )
        content = 'Hello, you\'ve entered the interactive poll maker. Please enter your question below.'
        accepted_emojis = {'\N{CROSS MARK}'}

        async def get_poll_options() -> typing.Union[str, bool]:
            deleted = True
            my_message: typing.Optional[discord.Message] = None

            def msg_check(msg: discord.Message):
                return msg.channel == ctx.channel and msg.author == ctx.author

            def rxn_check(rxn: discord.Reaction, usr: discord.User):
                return rxn.message == my_message and usr == ctx.author and str(rxn) in accepted_emojis

            while True:
                if deleted:
                    my_message = await ctx.send(content, embed=embed)
                    for emo in accepted_emojis:
                        await my_message.add_reaction(emo)
                    deleted = False
                futs = {
                    self.bot.loop.create_task(self.bot.wait_for('message', check=msg_check)),
                    self.bot.loop.create_task(self.bot.wait_for('reaction_add', check=rxn_check))
                }
                done, pending = await asyncio.wait(futs, timeout=60.0, return_when=asyncio.FIRST_COMPLETED)
                [fut.cancel() for fut in pending]
                params: typing.Union[discord.Message, tuple[discord.Reaction, discord.User]] = done.pop().result()
                if isinstance(params, discord.Message):
                    response = params.content.strip()
                    if not response:
                        await ctx.send('Message has no content', delete_after=10)
                        continue
                    if discord.utils.get(embed.fields, value=response):
                        await ctx.send('Duplicate options are not allowed')
                        continue
                else:
                    response = str(params[0]) == '\N{CROSS MARK}'
                await my_message.delete()
                yield response
                deleted = True

        async for i, resp in aioitertools.zip(range(11), get_poll_options()):
            if isinstance(resp, str):
                content = f'Hello, you\'ve entered the interactive poll maker. ' \
                          f'Please enter option {i + 1} below.'
                if i == 2:
                    accepted_emojis.add('\N{WHITE HEAVY CHECK MARK}')
                    embed.description += '\nReact with :white_check_mark: to exit'
                embed.add_field(
                    name='Question' if i == 0 else f'Option {1}',
                    value=resp
                )
            elif resp:
                return await ctx.send('Poll creation cancelled by user', delete_after=10)
            else:
                break
        timeout += (datetime.datetime.utcnow() - ctx.message.created_at).total_seconds()
        mgr = await PollManager.from_command(ctx, timeout, *[field.value for field in embed.fields])
        async with ctx.bot.sql as sql:  # type: asyncpg.Connection
            await sql.execute(
                'insert into polls (code, channel, owner, context, message, started, closes) '
                'values ($1, $2, $3, $4, $5, $6, $7)',
                *mgr
            )
        self.polls.append(mgr)
        mgr.start()

    @poll_cmd.error
    @interactive_poll_maker.error
    async def poll_create_error(self, ctx: MyContext, error: commands.CommandError):
        if isinstance(error, BadPollTimeArgument):
            await ctx.send('Invalid value for timeout. Try something like `300`, `60m`, `1w`, ...')
        else:
            await self.bot.send_tb(ctx, error, origin='poll new')

    @poll_cmd.command()
    async def cancel(self, ctx: MyContext, mgr: PollManager):
        """Cancel a running poll using a code. You must be the one who started the poll
        in the first place."""

        if ctx.author.id not in {mgr.owner_id, ctx.bot.owner_id}:
            raise NotPollOwner('You may not cancel this poll')
        mgr.cancel()

    @poll_cmd.command()
    async def show(self, ctx: MyContext, mgr: PollManager):
        """Gets poll info using a code."""

        if mgr.message is not None:
            await ctx.send(mgr.message.jump_url)
        else:
            if (channel := self.bot.get_channel(mgr.channel_id)) is None:
                mgr.cancel()
                raise NoPollFound('Channel not found')
            await ctx.send(f'https://discord.gg/channels/{channel.guild.id}/{mgr.channel_id}/{mgr.message_id}\n'
                           f'⚠ This jump URL may be invalid ⚠')
    
    @show.error
    @cancel.error
    async def poll_access_error(self, ctx: MyContext, exc: Exception):
        exc = getattr(exc, 'original', exc)
        await ctx.send(f'`{ctx.prefix}{ctx.invoked_with}` raised a(n) {exc.__class__.__name__}: {exc}')

    @poll_cmd.command()
    async def list(self, ctx: MyContext):
        """Lists all polls"""

        s = textwrap.indent('\n'.join(str(poll) for poll in self.polls if not poll.task.done()), '  ')
        if s:
            await ctx.send(f'Running polls: [\n{s}\n]')
        else:
            await ctx.send('No running polls')

    @BaseCog.listener()
    async def on_poll_end(self, mgr: PollManager):
        now = datetime.datetime.utcnow()
        async with self.bot.sql as sql:  # type: asyncpg.Connection
            await sql.execute('delete from poll_options where code = $1', mgr.hash)
            await sql.execute('delete from polls where code = $1', mgr.hash)
        if mgr in self.polls:
            self.polls.remove(mgr)
        channel = self.bot.get_channel(mgr.channel_id)
        if channel is None or mgr.message is None:
            return
        tally = Counter(mgr.votes.values())
        if now < mgr.stop_time:
            content2 = content = 'The poll was cancelled.'
        else:
            try:
                winner, count = max(tally.items(), key=operator.itemgetter(1))
                content = f'Poll closed, the winner is {mgr.emojis[winner]}'
                content2 = f'Poll `{mgr.hash}` has ended. ' \
                           f'The winner is {mgr.emojis[winner]} ' \
                           f'with {tally[winner]} vote(s).\n\n' \
                           f'Full results: {mgr.message.jump_url}'
            except (ValueError, IndexError):
                content = f'Poll closed, there is no winner'
                content2 = f'Poll `{mgr.hash}` has ended. ' \
                           f'No votes were recorded.\n\n' \
                           f'Full results: {mgr.message.jump_url}'
        embed: discord.Embed = mgr.message.embeds[0]
        desc = [f'{line} ({tally[i]})' for i, line in enumerate(mgr.options)]
        embed.description = '\n'.join(desc)
        await mgr.message.edit(content=content, embed=embed)
        await channel.send(content2)


def setup(bot: PikalaxBOT):
    bot.add_cog(Poll(bot))
