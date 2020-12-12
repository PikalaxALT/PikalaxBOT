import discord
from discord.ext import commands, tasks
from collections import Counter
from . import BaseCog
import time
import datetime
import io
import matplotlib.pyplot as plt
import typing
import traceback
from .utils.converters import PastTime
from .utils.mpl_time_axis import *
import numpy as np


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
        await sql.execute('create table if not exists memberstatus (guild_id bigint, timestamp timestamp, online integer, offline integer, dnd integer, idle integer)')
        await sql.execute('create unique index if not exists memberstatus_idx on memberstatus (guild_id, timestamp)')
        self.update_counters.start()

    @tasks.loop(seconds=30)
    async def update_counters(self):
        now = self.update_counters._last_iteration.replace(tzinfo=None)
        to_insert = []
        for guild in self.bot.guilds:
            counts = Counter(m.status for m in guild.members)
            to_insert.append([
                guild.id,
                now,
                counts[discord.Status.online],
                counts[discord.Status.offline],
                counts[discord.Status.dnd],
                counts[discord.Status.idle]
            ])
        async with self.bot.sql as sql:
            await sql.executemany('insert into memberstatus values ($1, $2, $3, $4, $5, $6) on conflict (guild_id, timestamp) do nothing', to_insert)

    @update_counters.before_loop
    async def update_counters_before_loop(self):
        await self.bot.wait_until_ready()

    @update_counters.error
    async def update_counters_error(self, error):
        s = ''.join(traceback.format_exception(error.__class__, error, error.__traceback__))
        content = f'Ignoring exception in MemberStatus.update_counters\n{s}'
        await self.bot.send_tb(content)

    @staticmethod
    def do_plot_status_history(buffer, history):
        times = list(history.keys())
        values = list(history.values())
        plt.figure()
        counts = {key: [v[key] for v in values] for key in MemberStatus.colormap}
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
    async def plot_status(self, ctx, hstart: typing.Union[PastTime, int] = 60, hend: typing.Union[PastTime, int] = 0):
        """Plot history of user status counts in the current guild."""
        if isinstance(hstart, int):
            hstart = ctx.message.created_at - datetime.timedelta(minutes=hstart)
        else:
            hstart = hstart.dt
        if isinstance(hend, int):
            hend = ctx.message.created_at - datetime.timedelta(minutes=hend)
        else:
            hend = hend.dt
        async with ctx.typing():
            fetch_start = time.perf_counter()
            async with self.bot.sql as sql:
                counts = {row[0]: {name: count for name, count in zip(discord.Status, row[1:])} for row in await sql.fetch('select timestamp, online, offline, dnd, idle from memberstatus where guild_id = $1 and timestamp >= $2 and timestamp < $3 order by timestamp', ctx.guild.id, hstart, hend)}
            fetch_end = time.perf_counter()
            if len(counts) > 1:
                buffer = io.BytesIO()
                start = time.perf_counter()
                await self.bot.loop.run_in_executor(None, MemberStatus.do_plot_status_history, buffer, counts)
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


def setup(bot):
    bot.add_cog(MemberStatus(bot))
