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

import discord
from discord.ext import commands, tasks
from collections import Counter
from . import *
import time
import datetime
import io
import matplotlib.pyplot as plt
import typing
from .utils.converters import PastTime
from .utils.mpl_time_axis import *
import numpy as np
from jishaku.functools import executor_function

from sqlalchemy import Column, BIGINT, INTEGER, TIMESTAMP, select, bindparam
from sqlalchemy.ext.asyncio import AsyncConnection
from sqlalchemy.dialects.postgresql import insert


class Memberstatus(BaseTable):
    guild_id = Column(BIGINT, primary_key=True)
    timestamp = Column(TIMESTAMP, primary_key=True)
    online = Column(INTEGER)
    offline = Column(INTEGER)
    dnd = Column(INTEGER)
    idle = Column(INTEGER)

    @classmethod
    async def update_counters(cls, sql: AsyncConnection, bot: PikalaxBOT, now: datetime.datetime):
        to_insert = [
            {'guild_id': guild.id, 'timestamp': now} | Counter(m.status.name for m in guild.members)
            for guild in bot.guilds
        ]
        statement = insert(cls).values(
            guild_id=bindparam('guild_id'),
            timestamp=bindparam('timestamp'),
            online=bindparam('online'),
            offline=bindparam('offline'),
            dnd=bindparam('dnd'),
            idle=bindparam('idle')
        )
        await sql.execute(statement, to_insert)

    @classmethod
    async def retrieve_counters(cls, sql: AsyncConnection, guild: discord.Guild, start: datetime.datetime, end: datetime.datetime):
        statement = select(
            [cls.timestamp, cls.online, cls.offline, cls.dnd, cls.idle]
        ).where(
            cls.guild_id == guild.id,
            cls.timestamp.between(start, end)
        ).order_by(cls.timestamp)
        result = await sql.execute(statement)
        return result.all()


class MemberStatus(BaseCog):
    """Commands for showing the historical distribution of user statuses
    (online, offline, etc.) in the guild."""

    colormap = {
        discord.Status.online: '#43B581',
        discord.Status.offline: '#747F8D',
        discord.Status.dnd: '#F04747',
        discord.Status.idle: '#FAA61A'
    }

    def cog_unload(self):
        self.update_counters.cancel()

    async def init_db(self, sql):
        await Memberstatus.create(sql)
        self.update_counters.start()

    @tasks.loop(seconds=30)
    async def update_counters(self):
        now = self.update_counters._last_iteration.replace(tzinfo=None)
        async with self.bot.sql as sql:
            await Memberstatus.update_counters(sql, self.bot, now)

    @update_counters.before_loop
    async def update_counters_before_loop(self):
        await self.bot.wait_until_ready()

    @update_counters.error
    async def update_counters_error(self, error: BaseException):
        await self.bot.send_tb(None, error, origin='MemberStatus.update_counters')

    @staticmethod
    @executor_function
    def do_plot_status_history(buffer: typing.BinaryIO, history: dict[datetime.datetime, Counter[discord.Status]]):
        times, values = zip(*history.items())
        plt.figure()
        counts: dict[discord.Status, list[int]] = {key: [v[key] for v in values] for key in MemberStatus.colormap}
        ax: plt.Axes = plt.gca()
        idxs = thin_points(len(times), 1000)
        for key, value in counts.items():
            ax.plot(np.array(times)[idxs], np.array(value)[idxs], c=MemberStatus.colormap[key], label=str(key).title())
        set_time_xlabs(ax, times)
        _, ymax = ax.get_ylim()
        ax.set_ylim(0, ymax)
        plt.xlabel('Time (UTC)')
        plt.ylabel('Number of users')
        plt.legend(loc=0)
        plt.tight_layout()
        plt.savefig(buffer)
        plt.close()

    @commands.guild_only()
    @commands.command(name='userstatus')
    async def plot_status(
            self,
            ctx: MyContext,
            hstart: PastTime = None,
            hend: PastTime = None
    ):
        """Plot history of user status counts in the current guild."""
        hstart = hstart.dt if hstart else ctx.message.created_at - datetime.timedelta(minutes=60)
        hend = hend.dt if hend else ctx.message.created_at
        async with ctx.typing():
            fetch_start = time.perf_counter()
            async with self.bot.sql as sql:
                counts: dict[datetime.datetime, Counter[discord.Status]] = {
                    row[0]: {
                        name: count
                        for name, count in zip(discord.Status, row[1:])
                    } for row in await Memberstatus.retrieve_counters(sql, ctx.guild, hstart, hend)
                }
            fetch_end = time.perf_counter()
            if len(counts) > 1:
                buffer = io.BytesIO()
                start = time.perf_counter()
                await MemberStatus.do_plot_status_history(buffer, counts)
                end = time.perf_counter()
                buffer.seek(0)
                msg = f'Fetched {len(counts)} records in {fetch_end - fetch_start:.3f}s\n' \
                      f'Rendered image in {end - start:.3f}s'
                file = discord.File(buffer, 'status.png')
            else:
                msg = f'Fetched {len(counts)} records in {fetch_end - fetch_start:.3f}s\n' \
                      f'Plotting failed'
                file = None
        await ctx.send(msg, file=file)


def setup(bot: PikalaxBOT):
    bot.add_cog(MemberStatus(bot))


def teardown(bot: PikalaxBOT):
    Memberstatus.unlink()
