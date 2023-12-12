import discord
from discord.ext import commands, tasks
from collections import defaultdict
import re
from datetime import datetime, timedelta
import json

# 必要なIntentsを設定
intents = discord.Intents.default()
intents.messages = True
intents.reactions = True
# intents.message_content = True

bot = commands.Bot(command_prefix='$', intents=intents, help_command=None)

# 日程提案のデータを保持する辞書
schedules = defaultdict(dict)
# メッセージIDと日付のマッピング
message_id_to_date = {}

# スケジュールを保存する関数
def save_schedules():
    with open('schedules.json', 'w') as f:
        json_schedules = {
            k: {
                'datetime': v['datetime'].strftime('%Y-%m-%d %H:%M'),
                'end_time': v['end_time'].strftime('%Y-%m-%d %H:%M') if 'end_time' in v else None,
                'votes': v.get('votes', []),
                'channel_id': v['channel_id'],
                'displayed': v.get('displayed', False)
            } for k, v in schedules.items()
        }
        json.dump(json_schedules, f, ensure_ascii=False, indent=4)


# スケジュールを読み込む関数
def load_schedules():
    try:
        with open('schedules.json', 'r') as f:
            loaded_schedules = json.load(f)
            return {
                k: {
                    'datetime': datetime.strptime(v['datetime'], '%Y-%m-%d %H:%M'),
                    'end_time': datetime.strptime(v['end_time'], '%Y-%m-%d %H:%M') if v['end_time'] else None,
                    'votes': v['votes'],
                    'channel_id': v['channel_id'],
                    'displayed': v.get('displayed', False)
                } for k, v in loaded_schedules.items()
            }
    except FileNotFoundError:
        return defaultdict(dict)


@bot.command(name='create_schedule', aliases=['cs'])
async def create_schedule(ctx, date_str: str, start_time_str: str, *args):
    # オプショナル引数の初期化
    endtime_hours = None
    overwrite = False

    # オプショナル引数の解析
    arg_iter = iter(args)
    for arg in arg_iter:
        if arg == '-e':  # 締切時間オプション
            endtime_hours = next(arg_iter, None)
            if endtime_hours is not None:
                try:
                    endtime_hours = int(endtime_hours)
                except ValueError:
                    await ctx.send('締切時間は整数で指定してください。')
                    return
        elif arg == '-o':  # 上書きオプション
            overwrite = True

    datetime_str = f"{date_str} {start_time_str}"
    try:
        scheduled_datetime = datetime.strptime(datetime_str, '%Y-%m-%d %H:%M')
    except ValueError:
        await ctx.send('日付と開始時間の形式が正しくありません。YYYY-MM-DD HH:MM形式で入力してください。')
        return

    # 締切時間の設定
    if endtime_hours is not None:
        endtime = datetime.now() + timedelta(hours=endtime_hours)
    else:
        endtime = datetime.now() + timedelta(hours=24)  # デフォルトの終了時間を設定

    schedule_key = scheduled_datetime.strftime('%Y-%m-%d')
    if schedule_key in schedules and not overwrite:
        await ctx.send(f'指定された日付 {schedule_key} には既にスケジュールが存在します。上書きするには "-o" を追加してください。')
        return

    # 日程の提案メッセージを送信
    # endtime_str = (endtime + timedelta(hours=9)).strftime('%Y-%m-%d %H:%M')
    endtime_str = (endtime).strftime('%Y-%m-%d %H:%M')
    message = await ctx.send(f'日程の提案: {datetime_str} 👍で賛成してください！\n（回答期限: {endtime_str}）')
    await message.add_reaction('👍')

    # 提案情報を記録または上書き
    schedules[schedule_key] = {
        'datetime': scheduled_datetime,
        'message_id': message.id,
        'channel_id': ctx.channel.id,
        'votes': [ctx.author.name],
        'end_time': endtime,  # 指定された終了時間
        'displayed': False
    }
    message_id_to_date[message.id] = schedule_key  # マッピングを追加

    # 新しいスケジュールを保存
    save_schedules()

@bot.command(name='extend_voting')
async def extend_voting(ctx, date_str: str, additional_hours: str):
    try:
        schedule_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        await ctx.send('日付の形式が正しくありません。YYYY-MM-DD形式で入力してください。')
        return

    try:
        additional_hours = int(additional_hours)
    except ValueError:
        await ctx.send('延長時間は整数で指定してください。')
        return

    if date_str in schedules:
        schedule = schedules[date_str]
        if datetime.now() < schedule['end_time']:
            schedule['end_time'] = datetime.now() + timedelta(hours=additional_hours)
            await ctx.send(f"{date_str} の投票締め切りを現在時刻から {additional_hours} 時間後に設定しました。")
            save_schedules()
        else:
            await ctx.send("投票期限は終了しています。投票の再開してください。")
    else:
        await ctx.send(f"{date_str} のスケジュールは見つかりませんでした。")

@bot.command(name='reopen_voting')
async def reopen_voting(ctx, date_str: str, additional_hours: int=1):
    try:
        schedule_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        await ctx.send('日付の形式が正しくありません。YYYY-MM-DD形式で入力してください。')
        return

    if date_str in schedules:
        schedule = schedules[date_str]
        if schedule['displayed']:
            schedule['end_time'] = datetime.now() + timedelta(hours=additional_hours)
            schedule['displayed'] = False  # 再投票を許可
            await ctx.send(f"{date_str} の投票を再開しました。追加で {additional_hours} 時間投票できます。")
            save_schedules()
        else:
            await ctx.send("このスケジュールはまだ確定していません。")
    else:
        await ctx.send(f"{date_str} のスケジュールは見つかりませんでした。")

@bot.event
async def on_reaction_add(reaction, user):
    if user == bot.user or reaction.emoji != '👍':
        return

    message_id = reaction.message.id
    if message_id in message_id_to_date:
        schedule_key = message_id_to_date[message_id]
        if user.name not in schedules[schedule_key]['votes']:
            schedules[schedule_key]['votes'].append(user.name)

@bot.command(name='show_schedules', aliases=['ss'])
async def show_schedules(ctx, *args):
    # オプショナル引数の初期化
    show_all = False

    arg_iter = iter(args)
    response = "確定スケジュール:\n"
    for arg in arg_iter:
        if arg == '-a':
            show_all = True
            response = "全スケジュール:\n"

    now = datetime.now()
    for date, schedule in schedules.items():
        if (not show_all) and schedule['datetime'] >= now and len(schedule['votes']) >= 3:
            response += f"- {date}: {', '.join(schedule['votes'])}\n"
        elif show_all and schedule['datetime'] >= now: 
            response += f"- {date}: {', '.join(schedule['votes'])} (同意数: {len(schedule['votes'])})\n"
    await ctx.send(response)

@bot.command(name='search_schedule')
async def search_schedule(ctx, date_str: str):
    # 日付形式のバリデーション
    try:
        search_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        await ctx.send('日付の形式が正しくありません。YYYY-MM-DD形式で入力してください。')
        return

    # 指定された日付のスケジュールを検索
    response = f"{date_str} のスケジュール:\n"
    found = False
    for date, schedule in schedules.items():
        if schedule['datetime'].date() == search_date:
            datetime_str = schedule['datetime'].strftime('%Y-%m-%d %H:%M')
            votes_str = ', '.join(schedule.get('votes', []))
            response += f"- {datetime_str}: {votes_str}\n"
            found = True

    if not found:
        response += "スケジュールは見つかりませんでした。"

    await ctx.send(response)

@bot.command(name='hiroto')
async def hiroto(ctx):
    await ctx.send("相変わらずヒロトはヒロトしてますね...")

@bot.command(name='sorry')
async def sorry(ctx):
    await ctx.send("ごめんなさい．")

@bot.command(name='hasegawa')
async def hasegawa(ctx):
    await ctx.send("長谷川を許すな")

@bot.command(name='クリスマス')
async def Xmas(ctx):
    await ctx.send("https://tenor.com/view/rudolph-cute-christmas-decorations-christmas-tree-reindeer-gif-4892086250386727158")

@bot.command(name='delete_schedule')
async def delete_schedule(ctx, date: str):
    if date in schedules and len(schedules[date]['votes']) >= 3:
        del schedules[date]
        await ctx.send(f"{date} のスケジュールを削除しました。")
        save_schedules()
    else:
        await ctx.send(f"{date} は削除できるスケジュールではありません。")

@bot.command(name='help')
async def help_command(ctx):
    help_text = """
    **ヘルプ**

    **$create_schedule (cs) [日付] [開始時間] [オプション]**
    新しいスケジュールを作成します。例: $cs 2023-12-25 15:00
    オプション:
    -e [時間]: 投票の締め切り時間を設定。デフォルトは24時間後。
    -o: 既存のスケジュールを上書き。

    **$extend_voting [日付] [追加時間]**
    指定された日付の投票期限を延長します。例: $extend_voting 2023-12-25 2

    **$reopen_voting [日付] [追加時間]**
    確定済みのスケジュールの投票を再開します。例: $reopen_voting 2023-12-25 1

    **$show_schedules (ss) [-a]**
    確定済みのスケジュールを表示します。-a オプションで全スケジュールを表示。例: $ss -a

    **$search_schedule [日付]**
    指定された日付のスケジュールを検索します。例: $search_schedule 2023-12-25

    **$delete_schedule [日付]**
    指定された日付のスケジュールを削除します。例: $delete_schedule 2023-12-25

    **$hiroto**
    ヒロトに関するコメントを表示します。

    **$sorry**
    謝罪のコメントを表示します。
    """
    await ctx.send(help_text)


@tasks.loop(minutes=1)
async def check_schedules():
    now = datetime.now()
    for schedule_key, schedule in list(schedules.items()):
        if now >= schedule['end_time'] and not schedule['displayed']:
            voters = ', '.join(schedule.get('votes', []))
            datetime_str = schedule['datetime'].strftime('%Y-%m-%d %H:%M')
            channel = bot.get_channel(schedule['channel_id'])
            if(len(schedule['votes'])==1):
                await channel.send(f"日程 {datetime_str} の投票結果: たったの1票. {voters}さんって人望ないんですね...")
            else:
                await channel.send(f"日程 {datetime_str} の投票結果: {len(schedule['votes'])} 票。参加者: {voters}")
            schedule['displayed'] = True  # 表示済みに更新
            save_schedules()

@bot.event
async def on_ready():
    global schedules
    schedules = load_schedules()  # スケジュールを読み込む
    print(f'Logged in as {bot.user.name}')
    if not check_schedules.is_running():
        check_schedules.start()

def load_config():
    with open('config.json', 'r') as file:
        return json.load(file)


bot.run(load_config()['bot_token'])



