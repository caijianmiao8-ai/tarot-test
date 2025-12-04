"""
重生模拟器 - Reincarnation Simulator
基于真实全球人口出生率数据的趣味游戏
"""
import random
import secrets
from flask import Blueprint, render_template, make_response, request, jsonify

SLUG = "reincarnation"

def get_meta():
    return {
        "slug": SLUG,
        "title": "重生模拟器",
        "subtitle": "下一世，你将出生在哪里？",
        "path": f"/g/{SLUG}/",
        "tags": ["Game", "Fun", "Random"]
    }

bp = Blueprint(
    SLUG, __name__,
    template_folder="templates",
    static_folder="static",
    static_url_path=f"/static/games/{SLUG}",
)

# 全球人口出生数据 (基于2023-2024年联合国和世界银行数据)
# births: 年出生人数（千人）
BIRTH_DATA = [
    {
        "country": "印度",
        "country_en": "India",
        "flag": "🇮🇳",
        "births": 24000,
        "description": "在恒河边听着宝莱坞音乐长大，你可能成为下一个硅谷CEO",
        "traits": ["人口大国", "IT强国", "咖喱美食", "瑜伽发源地"],
        "fun_fact": "印度有22种官方语言，出生就是语言天才！",
        "probability_note": "全球约17%的婴儿出生在这里"
    },
    {
        "country": "中国",
        "country_en": "China",
        "flag": "🇨🇳",
        "births": 10000,
        "description": "从小卷到大，但至少你能用筷子夹起任何东西",
        "traits": ["基建狂魔", "美食天堂", "5000年文明", "移动支付天堂"],
        "fun_fact": "出生即可体验全球最快的高铁和外卖速度",
        "probability_note": "全球约7%的新生儿来自这里"
    },
    {
        "country": "尼日利亚",
        "country_en": "Nigeria",
        "flag": "🇳🇬",
        "births": 7000,
        "description": "非洲最大经济体，诺莱坞电影产量仅次于宝莱坞",
        "traits": ["非洲巨人", "石油大国", "音乐热土", "创业热情"],
        "fun_fact": "尼日利亚有超过500种语言，你天生就是语言学家！",
        "probability_note": "全球约5%的婴儿在这里诞生"
    },
    {
        "country": "巴基斯坦",
        "country_en": "Pakistan",
        "flag": "🇵🇰",
        "births": 5500,
        "description": "在喜马拉雅山脚下品尝正宗烤肉，板球是全民信仰",
        "traits": ["板球狂热", "山地美景", "香料王国", "友谊之国"],
        "fun_fact": "世界第二高峰K2就在这里，出生就能看到8000米雪山",
        "probability_note": "全球约4%的新生儿"
    },
    {
        "country": "印度尼西亚",
        "country_en": "Indonesia",
        "flag": "🇮🇩",
        "births": 4500,
        "description": "一万七千个岛屿，你可能一辈子都探索不完自己的国家",
        "traits": ["千岛之国", "火山王国", "潜水天堂", "咖啡原产地"],
        "fun_fact": "这里有世界上最多的火山，生活自带刺激感！",
        "probability_note": "全球约3.2%的婴儿"
    },
    {
        "country": "埃塞俄比亚",
        "country_en": "Ethiopia",
        "flag": "🇪🇹",
        "births": 3500,
        "description": "咖啡的诞生地，拥有独特的13个月历法",
        "traits": ["咖啡故乡", "古老文明", "马拉松强国", "独特历法"],
        "fun_fact": "这里是人类的起源地之一，回到人类的摇篮！",
        "probability_note": "全球约2.5%的新生儿"
    },
    {
        "country": "刚果民主共和国",
        "country_en": "DR Congo",
        "flag": "🇨🇩",
        "births": 3500,
        "description": "拥有世界第二大热带雨林，矿产资源堪称地球宝库",
        "traits": ["矿产富国", "雨林王国", "音乐天赋", "河流之国"],
        "fun_fact": "刚果河是世界第二深的河流，深度达220米！",
        "probability_note": "全球约2.5%的婴儿"
    },
    {
        "country": "美国",
        "country_en": "United States",
        "flag": "🇺🇸",
        "births": 3500,
        "description": "自由的国度，从硅谷到好莱坞，梦想还是要有的",
        "traits": ["科技中心", "好莱坞", "超级大国", "移民熔炉"],
        "fun_fact": "平均每个美国人一生会搬家11次，你注定是个冒险家",
        "probability_note": "全球约2.5%的新生儿"
    },
    {
        "country": "孟加拉国",
        "country_en": "Bangladesh",
        "flag": "🇧🇩",
        "births": 3000,
        "description": "世界上人口密度最高的国家之一，你永远不会感到孤单",
        "traits": ["河流之国", "纺织大国", "文学传统", "芒果天堂"],
        "fun_fact": "这里有世界上最长的不间断海滩，长达120公里！",
        "probability_note": "全球约2.1%的婴儿"
    },
    {
        "country": "巴西",
        "country_en": "Brazil",
        "flag": "🇧🇷",
        "births": 2800,
        "description": "桑巴、足球、狂欢节，这里的DNA里就写着快乐",
        "traits": ["足球王国", "亚马逊雨林", "狂欢节", "咖啡大国"],
        "fun_fact": "巴西人平均每年消耗5公斤咖啡豆，出生就是咖啡因战士",
        "probability_note": "全球约2%的新生儿"
    },
    {
        "country": "埃及",
        "country_en": "Egypt",
        "flag": "🇪🇬",
        "births": 2500,
        "description": "金字塔的守护者，五千年文明就在你家门口",
        "traits": ["古文明", "金字塔", "尼罗河", "历史宝库"],
        "fun_fact": "埃及有138座金字塔，你的祖先可能建造过它们！",
        "probability_note": "全球约1.8%的婴儿"
    },
    {
        "country": "墨西哥",
        "country_en": "Mexico",
        "flag": "🇲🇽",
        "births": 2000,
        "description": "玉米饼和龙舌兰的故乡，亡灵节比春节还热闹",
        "traits": ["美食天堂", "玛雅文明", "龙舌兰", "亡灵节"],
        "fun_fact": "墨西哥是巧克力的发源地，这里的人发明了热可可！",
        "probability_note": "全球约1.4%的新生儿"
    },
    {
        "country": "菲律宾",
        "country_en": "Philippines",
        "flag": "🇵🇭",
        "births": 2000,
        "description": "七千多个岛屿，跳岛游是你的日常通勤方式",
        "traits": ["千岛之国", "热带天堂", "友善民族", "卡拉OK文化"],
        "fun_fact": "菲律宾人平均每天发送4.5亿条短信，你生来就是社交达人",
        "probability_note": "全球约1.4%的婴儿"
    },
    {
        "country": "坦桑尼亚",
        "country_en": "Tanzania",
        "flag": "🇹🇿",
        "births": 2000,
        "description": "乞力马扎罗山和塞伦盖蒂大草原，与野生动物为邻",
        "traits": ["野生动物天堂", "非洲屋脊", "原始部落", "宝石之国"],
        "fun_fact": "这里有超过120个部落，每个都有独特的文化和语言",
        "probability_note": "全球约1.4%的新生儿"
    },
    {
        "country": "俄罗斯",
        "country_en": "Russia",
        "flag": "🇷🇺",
        "births": 1400,
        "description": "世界上最大的国家，你需要11个时区才能横穿祖国",
        "traits": ["战斗民族", "广袤领土", "太空强国", "文学艺术"],
        "fun_fact": "俄罗斯的森林面积比亚马逊还大，出生就是森林之子",
        "probability_note": "全球约1%的婴儿"
    },
    {
        "country": "越南",
        "country_en": "Vietnam",
        "flag": "🇻🇳",
        "births": 1400,
        "description": "河粉和咖啡的天堂，摩托车比汽车还多",
        "traits": ["河粉之国", "咖啡文化", "悠久历史", "海滩美景"],
        "fun_fact": "越南人均咖啡消费量全球第二，你天生就是咖啡鉴赏家",
        "probability_note": "全球约1%的新生儿"
    },
    {
        "country": "日本",
        "country_en": "Japan",
        "flag": "🇯🇵",
        "births": 770,
        "description": "从武士刀到电子游戏，传统与未来的完美融合",
        "traits": ["动漫王国", "科技强国", "长寿之国", "匠人精神"],
        "fun_fact": "日本有超过5万家拉面店，出生就能吃遍各种拉面",
        "probability_note": "全球约0.55%的婴儿"
    },
    {
        "country": "德国",
        "country_en": "Germany",
        "flag": "🇩🇪",
        "births": 750,
        "description": "啤酒、香肠和严谨，你的时间观念会精确到秒",
        "traits": ["工业强国", "啤酒文化", "哲学摇篮", "足球劲旅"],
        "fun_fact": "德国有超过1500种香肠和1300种啤酒，吃喝不愁",
        "probability_note": "全球约0.54%的新生儿"
    },
    {
        "country": "英国",
        "country_en": "United Kingdom",
        "flag": "🇬🇧",
        "births": 700,
        "description": "绅士淑女的国度，下午茶是人生大事",
        "traits": ["绅士文化", "哈利波特", "足球起源地", "摇滚发源地"],
        "fun_fact": "英国人平均每年喝掉165杯茶，出生就是品茶大师",
        "probability_note": "全球约0.5%的婴儿"
    },
    {
        "country": "法国",
        "country_en": "France",
        "flag": "🇫🇷",
        "births": 680,
        "description": "浪漫之都，红酒、奶酪和埃菲尔铁塔是你的日常",
        "traits": ["浪漫之国", "美食天堂", "时尚之都", "艺术殿堂"],
        "fun_fact": "法国有超过400种奶酪，你能每天吃不同的奶酪一整年",
        "probability_note": "全球约0.49%的新生儿"
    },
    {
        "country": "韩国",
        "country_en": "South Korea",
        "flag": "🇰🇷",
        "births": 240,
        "description": "K-POP和泡菜的故乡，网速快到让你怀疑人生",
        "traits": ["电竞强国", "K-POP", "美妆大国", "5G先驱"],
        "fun_fact": "韩国的平均网速世界第一，出生就是网速自由",
        "probability_note": "全球约0.17%的婴儿"
    },
    {
        "country": "澳大利亚",
        "country_en": "Australia",
        "flag": "🇦🇺",
        "births": 310,
        "description": "袋鼠比人多的国度，冲浪和烧烤是生活方式",
        "traits": ["袋鼠之国", "冲浪天堂", "原住民文化", "独特生态"],
        "fun_fact": "澳大利亚有超过1万个海滩，你可以每天去不同的海滩27年",
        "probability_note": "全球约0.22%的新生儿"
    },
    {
        "country": "加拿大",
        "country_en": "Canada",
        "flag": "🇨🇦",
        "births": 380,
        "description": "枫叶之国，冰球比足球更重要，全民都会说'Sorry'",
        "traits": ["枫叶之国", "冰球王国", "多元文化", "自然美景"],
        "fun_fact": "加拿大的森林覆盖率达38.7%，出生就能拥抱大自然",
        "probability_note": "全球约0.27%的婴儿"
    },
    {
        "country": "阿根廷",
        "country_en": "Argentina",
        "flag": "🇦🇷",
        "births": 650,
        "description": "探戈和梅西的故乡，牛排大到一个人吃不完",
        "traits": ["足球强国", "探戈发源地", "牛排天堂", "巴塔哥尼亚"],
        "fun_fact": "阿根廷人均牛肉消费量世界第一，天生肉食动物",
        "probability_note": "全球约0.46%的新生儿"
    },
    {
        "country": "南非",
        "country_en": "South Africa",
        "flag": "🇿🇦",
        "births": 1100,
        "description": "彩虹之国，11种官方语言让你天生语言天才",
        "traits": ["彩虹之国", "野生动物", "钻石之国", "多元文化"],
        "fun_fact": "南非有三个首都，一出生就拥有三个家乡",
        "probability_note": "全球约0.79%的婴儿"
    }
]

# 计算总出生人数
TOTAL_BIRTHS = sum(d["births"] for d in BIRTH_DATA)

# 为每个国家计算概率
for data in BIRTH_DATA:
    data["probability"] = data["births"] / TOTAL_BIRTHS * 100


def _ensure_sid(resp):
    """确保用户有session ID"""
    if request.cookies.get("sid"):
        return resp
    sid = secrets.token_hex(16)
    resp.set_cookie("sid", sid, max_age=60*60*24*730, httponly=True, samesite="Lax")
    return resp


def _weighted_random_country():
    """基于出生率的加权随机选择"""
    weights = [d["births"] for d in BIRTH_DATA]
    chosen = random.choices(BIRTH_DATA, weights=weights, k=1)[0]
    return chosen


@bp.get("/")
@bp.get("")
def page():
    """游戏主页"""
    resp = make_response(render_template(f"games/{SLUG}/index.html"))
    return _ensure_sid(resp)


@bp.post("/api/reincarnate")
def api_reincarnate():
    """重生API - 返回随机国家"""
    try:
        country_data = _weighted_random_country()
        return jsonify({
            "ok": True,
            "result": country_data
        })
    except Exception as e:
        return jsonify({
            "ok": False,
            "error": str(e)
        }), 500


@bp.get("/api/countries")
def api_countries():
    """获取所有国家数据（用于统计展示）"""
    return jsonify({
        "ok": True,
        "countries": BIRTH_DATA,
        "total_births": TOTAL_BIRTHS
    })


def get_blueprint():
    return bp
