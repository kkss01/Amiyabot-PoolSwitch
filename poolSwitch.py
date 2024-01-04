import os
import re
import random
import shutil
import importlib
from typing import List
from core import Message, Chain, log
from core.util import any_match, create_dir, read_yaml
from core.database.bot import Pool
from core import AmiyaBotPluginInstance
from amiyabot.util import temp_sys_path
from amiyabot.adapters.mirai import MiraiBotInstance, MiraiForwardMessage
from amiyabot.adapters.cqhttp import CQHttpBotInstance, CQHTTPForwardMessage

curr_dir = os.path.dirname(__file__)


class PoolSwitchPluginInstance(AmiyaBotPluginInstance):
    def install(self):
        Config.update()


class Config:
    show_pool_list = True

    @staticmethod
    def update():
        try:
            Config.show_pool_list = bot.get_config('showPoolList')

        except TypeError:
            log.warning('卡池智能切换: 配置文件读取错误, 请检查')
            Config.show_pool_list = True

    @staticmethod
    def abandon_yaml(config_path: str):
        if os.path.exists(config_path):
            dir_name = os.path.splitext(config_path)[0] + '(已弃用).yaml'
            os.rename(config_path, dir_name)


bot = PoolSwitchPluginInstance(
    name='卡池智能切换',
    version='1.8.3',
    plugin_id='kkss-pool-switch',
    plugin_type='',
    description='让兔兔更聪明地切换卡池',
    document=f'{curr_dir}/README.md',
    global_config_default=f'{curr_dir}/default.json',
    global_config_schema=f'{curr_dir}/schema.json',
)


def replace_items_to_same(text: str, target: list, after: str):
    for item in target:
        text = text.replace(item, after)

    return text


def get_prefix_name():
    prefix: list = read_yaml('config/prefix.yaml').prefix_keywords
    return '兔兔' if '兔兔' in prefix else prefix[0]


def remove_prefix_keywords(text: str):
    for item in bot.get_container('prefix_keywords'):
        if item in text:
            text = text.replace(item, '')
            return text
    return text


async def import_gacha():
    plug_dir = os.listdir(f'{curr_dir}/../')

    for dir_name in plug_dir:
        dir_path = f'{curr_dir}/../{dir_name}'

        if os.path.isfile(dir_path):
            continue

        if os.path.basename(dir_path).startswith('amiyabot-arknights-gacha'):
            with temp_sys_path(os.path.dirname(os.path.abspath(dir_path))):
                gacha = importlib.import_module(os.path.basename(dir_path))
            return gacha


async def get_description():
    Config.update()

    pk = get_prefix_name()

    desc = ''
    desc += f'# 使用说明  \n'
    desc += f'以下指令均可随时使用, 无需在切换前查看卡池列表\n'
    desc += f'<br>&emsp;( 指令中的括号 [ ] 不需要输入 )\n'
    desc += f'- <font color=Green>**`{pk}卡池[干员名]` 可直接切换到该干员首次up的卡池 <br>**</font> \n'
    desc += f'&emsp;( 支持别名 )\n'
    desc += f'- `{pk}最新卡池` 可切换最新卡池 **(不包含常驻/联合/中坚寻访)** \n'
    desc += f'- `{pk}随机卡池` 可随机切换卡池 \n'
    desc += f'- `{pk}常驻卡池` 可切换到常驻寻访 \n'
    desc += f'- `{pk}中坚卡池` 可切换到中坚寻访 \n'
    desc += f'- `{pk}联合卡池` 可直切换到联合寻访 (可能更新不及时) \n'

    if Config.show_pool_list:
        desc += f'- `{pk}卡池[卡池编号]` 可切换到卡池列表中的对应卡池 \n'
        desc += f'- `{pk}卡池[卡池名称]` 可切换到对应卡池 \n'

    desc += f'<br><br><font color="#999"> (各用户卡池独立) </font>'

    return desc


async def get_pool_menu() -> str:
    text = '这是可更换的卡池列表：\n\n'
    pools = []
    max_len = 0
    all_pools: List[Pool] = Pool.select()
    
    text += '|卡池名称|卡池名称|卡池名称|卡池名称|\n|----|----|----|----|\n'

    for index, item in enumerate(all_pools):
        text += f'|<span style="color: red; padding-right: 5px; font-weight: bold;">{index + 1}</span> {item.pool_name}'
        if (index + 1) % 4 == 0:
            text += '|\n'

    text += '\n\n>此页面由 **卡池智能切换** 提供'

    return text


async def match_pool(key: str, text: str):
    text = remove_prefix_keywords(text)

    text = text.replace(key, '')

    all_pools: List[Pool] = Pool.select()

    if '最新' in text:
        return all_pools[-1]

    if '随机' in text:
        return random.choice(all_pools)

    if '常驻' in text:
        return all_pools[0]

    if '中坚' in text:
        return all_pools[1]

    if '联合' in text:
        return all_pools[2]

    Config.update()

    if Config.show_pool_list:
        r = re.search(r'(\d+)', text)
        if r:
            index = int(r.group(1)) - 1
            if 0 <= index < len(all_pools):
                return all_pools[index]

    candidate = ''
    target_pool = None
    for pool in all_pools:
        if pool.id < 4:
            continue

        pickup: List[str] = pool.pickup_6.split(',') + pool.pickup_5.split(',') + pool.pickup_4.split(',')

        if Config.show_pool_list and pool.pool_name in text:
            return pool

        match = any_match(text, pickup) # 取名字长的干员
        if match and len(match) > len(candidate):
            candidate = match
            target_pool = pool

    if target_pool:
        return target_pool


async def pool_verify(data: Message):
    text = data.text

    key = any_match(text, ['卡池', '池子'])
    if not key:
        return False

    text = remove_prefix_keywords(text)

    if not text or '更新' in text or '同步' in text:
        return False

    return True, 6, key

 
@bot.on_message(verify=pool_verify)
async def _(data: Message):
    key = data.verify.keypoint

    text = remove_prefix_keywords(data.text).replace(key, '')

    search = replace_items_to_same(text, ['列表', '切换', '菜单', '查看'], '')

    targetPool = await match_pool(key=key, text=text)

    gacha = await import_gacha()

    if targetPool:
        if not gacha:
            log.warning('卡池智能切换: 模拟抽卡模块引入失败')
            return Chain(data).text('模拟抽卡模块引入失败')

        change_res = gacha.main.change_pool(item=targetPool, user_id=data.user_id)
        if change_res[1]:
            return Chain(data).image(change_res[1]).text_image(change_res[0])
        return Chain(data).text_image(change_res[0])
    
    if search:
        text = f'没有找到符合条件的卡池: "{search}"    \n' \
                '可能的原因:  \n' \
                '干员名包含错别字  \n' \
                '该干员没有up的卡池  \n' \
                '该卡池已过期或未更新'

    source = type(data.instance)
    if source is CQHttpBotInstance:
        forward = CQHTTPForwardMessage(data)
    elif source is MiraiBotInstance:
        forward = MiraiForwardMessage(data)
    else:
        chain = Chain(data).text(text).markdown(await get_description())
        if Config.show_pool_list:
            chain.markdown(await get_pool_menu())
        return chain
    
    if search:
        await forward.add_message(Chain().text(text),
                                    user_id=data.instance.appid, nickname='提示')    
    
    chain = Chain().markdown(await get_description())

    if Config.show_pool_list:
        chain.markdown(await get_pool_menu())

    await forward.add_message(chain, user_id=data.user_id, nickname='卡池列表')

    await forward.send()
