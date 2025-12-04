"""
重生模拟器 - Reincarnation Simulator V2
基于真实全球人口出生率数据的趣味游戏 - 现代化版本，支持地图可视化
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

# 全球人口出生数据 V2 (基于2023-2024年联合国和世界银行数据)
# 新增：continent（大洲）、region（地区）、coordinates（地图坐标）、color（主题色）
BIRTH_DATA = [
    {
        "country": "印度",
        "country_en": "India",
        "flag": "🇮🇳",
        "continent": "亚洲",
        "region": "南亚",
        "births": 24000,
        "coordinates": {"lat": 20.5937, "lng": 78.9629},
        "color": "#FF9933",
        "description": "🎬 在恒河边听着宝莱坞音乐长大，你可能成为下一个硅谷CEO，也可能成为板球巨星",
        "lifestyle": "每天被22种语言包围，早餐吃咖喱，午餐吃咖喱，晚餐还是咖喱（但每次都不一样！）",
        "traits": ["人口大国", "IT强国", "咖喱天堂", "瑜伽发源地", "宝莱坞"],
        "fun_fact": "💡 印度每年制作超过1800部电影，比好莱坞还多！你从小就是影视达人",
        "life_expectancy": "70岁",
        "probability_note": "全球约17%的婴儿出生在这里",
        "famous_for": ["泰姬陵", "IT产业", "香料贸易", "瑜伽修行"]
    },
    {
        "country": "中国",
        "country_en": "China",
        "flag": "🇨🇳",
        "continent": "亚洲",
        "region": "东亚",
        "births": 10000,
        "coordinates": {"lat": 35.8617, "lng": 104.1954},
        "color": "#DE2910",
        "description": "🏗️ 从小卷到大，但至少你拥有全球最快的高铁、最快的外卖和最快的手机支付",
        "lifestyle": "早上吃煎饼果子，中午叫外卖（15分钟必达），晚上刷短视频到凌晨。周末要么在补习班，要么在去补习班的路上",
        "traits": ["基建狂魔", "美食天堂", "5000年文明", "移动支付王国", "电商帝国"],
        "fun_fact": "💡 中国有超过10亿移动支付用户，你可能一出生就不需要现金了",
        "life_expectancy": "78岁",
        "probability_note": "全球约7%的新生儿来自这里",
        "famous_for": ["长城", "高铁", "移动支付", "外卖文化"]
    },
    {
        "country": "尼日利亚",
        "country_en": "Nigeria",
        "flag": "🇳🇬",
        "continent": "非洲",
        "region": "西非",
        "births": 7000,
        "coordinates": {"lat": 9.0820, "lng": 8.6753},
        "color": "#008751",
        "description": "🎵 非洲最大经济体，Afrobeats音乐响彻全球，诺莱坞电影产量仅次于宝莱坞",
        "lifestyle": "在拉各斯的街头感受非洲活力，白天做生意，晚上跳舞。每个人都是天生的创业者和音乐家",
        "traits": ["非洲巨人", "石油大国", "音乐之都", "创业热土", "文化多元"],
        "fun_fact": "💡 尼日利亚有超过500种语言和250个民族，你的朋友圈会非常国际化",
        "life_expectancy": "55岁",
        "probability_note": "全球约5%的婴儿在这里诞生",
        "famous_for": ["Afrobeats", "诺莱坞", "石油", "多元文化"]
    },
    {
        "country": "巴基斯坦",
        "country_en": "Pakistan",
        "flag": "🇵🇰",
        "continent": "亚洲",
        "region": "南亚",
        "births": 5500,
        "coordinates": {"lat": 30.3753, "lng": 69.3451},
        "color": "#01411C",
        "description": "🏔️ 在喜马拉雅山脚下长大，品尝世界上最正宗的烤肉，板球是你的宗教",
        "lifestyle": "每天喝奶茶配烤肉串，周末全民看板球比赛。世界第二高峰K2就在你家隔壁",
        "traits": ["板球狂热", "山地王国", "香料之国", "好客民族", "烤肉天堂"],
        "fun_fact": "💡 世界14座8000米以上雪山中的5座都在巴基斯坦，你是天生的登山家",
        "life_expectancy": "67岁",
        "probability_note": "全球约4%的新生儿",
        "famous_for": ["K2雪山", "板球", "巴斯马蒂米", "苏菲派音乐"]
    },
    {
        "country": "印度尼西亚",
        "country_en": "Indonesia",
        "flag": "🇮🇩",
        "continent": "亚洲",
        "region": "东南亚",
        "births": 4500,
        "coordinates": {"lat": -0.7893, "lng": 113.9213},
        "color": "#FF0000",
        "description": "🏝️ 一万七千个岛屿任你探索，火山、海滩、雨林，每天都是新的冒险",
        "lifestyle": "早上冲浪，中午潜水，晚上喝咖啡看日落。地震和火山喷发是生活的一部分，但这让人生更刺激",
        "traits": ["千岛之国", "火山王国", "潜水天堂", "咖啡原产地", "生物多样性"],
        "fun_fact": "💡 印尼是世界上最大的岛国，你可能需要一辈子才能走遍所有岛屿",
        "life_expectancy": "72岁",
        "probability_note": "全球约3.2%的婴儿",
        "famous_for": ["巴厘岛", "婆罗浮屠", "火山", "珊瑚礁"]
    },
    {
        "country": "美国",
        "country_en": "United States",
        "flag": "🇺🇸",
        "continent": "北美洲",
        "region": "北美",
        "births": 3500,
        "coordinates": {"lat": 37.0902, "lng": -95.7129},
        "color": "#B22234",
        "description": "🗽 自由的国度，从硅谷到好莱坞，从华尔街到NASA，梦想在这里起飞",
        "lifestyle": "汉堡、可乐、炸鸡是标配。开车30分钟去买个牛奶很正常。信用卡从娃娃抓起",
        "traits": ["科技中心", "好莱坞", "超级大国", "多元文化", "创新引擎"],
        "fun_fact": "💡 美国人平均一生会搬家11次，你注定是个爱冒险的流浪者",
        "life_expectancy": "79岁",
        "probability_note": "全球约2.5%的新生儿",
        "famous_for": ["硅谷", "好莱坞", "NASA", "华尔街"]
    },
    {
        "country": "巴西",
        "country_en": "Brazil",
        "flag": "🇧🇷",
        "continent": "南美洲",
        "region": "南美",
        "births": 2800,
        "coordinates": {"lat": -14.2350, "lng": -51.9253},
        "color": "#009B3A",
        "description": "⚽ 桑巴、足球、狂欢节，快乐刻在DNA里。亚马逊雨林是你家后院",
        "lifestyle": "每天踢球、跳舞、喝咖啡。狂欢节时全国放假一周。足球不是运动，是信仰",
        "traits": ["足球王国", "亚马逊雨林", "狂欢节", "桑巴舞", "咖啡大国"],
        "fun_fact": "💡 巴西人均每年消耗5公斤咖啡豆，你从小就是咖啡因战士",
        "life_expectancy": "76岁",
        "probability_note": "全球约2%的新生儿",
        "famous_for": ["足球", "狂欢节", "亚马逊", "基督像"]
    },
    {
        "country": "日本",
        "country_en": "Japan",
        "flag": "🇯🇵",
        "continent": "亚洲",
        "region": "东亚",
        "births": 770,
        "coordinates": {"lat": 36.2048, "lng": 138.2529},
        "color": "#BC002D",
        "description": "🗾 从武士到动漫，从寿司到新干线，传统与未来在这里完美融合",
        "lifestyle": "便利店比你家都近，自动贩卖机遍布街头。工作认真到让人怀疑人生，但拉面真的很好吃",
        "traits": ["动漫王国", "科技强国", "匠人精神", "长寿之国", "礼仪之邦"],
        "fun_fact": "💡 日本有超过5万家拉面店，你可以每天吃不同的拉面140年",
        "life_expectancy": "85岁",
        "probability_note": "全球约0.55%的婴儿",
        "famous_for": ["动漫", "寿司", "富士山", "新干线"]
    },
    {
        "country": "德国",
        "country_en": "Germany",
        "flag": "🇩🇪",
        "continent": "欧洲",
        "region": "西欧",
        "births": 750,
        "coordinates": {"lat": 51.1657, "lng": 10.4515},
        "color": "#000000",
        "description": "🍺 啤酒、香肠、严谨，工程师文化渗透生活。你的时间观念会精确到秒",
        "lifestyle": "早餐吃面包配香肠，午餐继续吃香肠，晚餐喝啤酒吃香肠。周日商店全部关门，逼你提前规划人生",
        "traits": ["工业强国", "啤酒文化", "严谨认真", "足球劲旅", "哲学摇篮"],
        "fun_fact": "💡 德国有超过1500种香肠和1300种啤酒，吃喝一辈子不重样",
        "life_expectancy": "81岁",
        "probability_note": "全球约0.54%的新生儿",
        "famous_for": ["汽车工业", "啤酒节", "新天鹅堡", "足球"]
    },
    {
        "country": "英国",
        "country_en": "United Kingdom",
        "flag": "🇬🇧",
        "continent": "欧洲",
        "region": "西欧",
        "births": 700,
        "coordinates": {"lat": 55.3781, "lng": -3.4360},
        "color": "#C8102E",
        "description": "☕ 绅士淑女的国度，下午茶是人生大事。天气是永恒的话题（因为真的很难预测）",
        "lifestyle": "每天至少5杯茶，见人先聊天气，排队是一种艺术。下雨不打伞显得更本地",
        "traits": ["绅士文化", "足球起源地", "文学殿堂", "皇室传统", "摇滚发源地"],
        "fun_fact": "💡 英国人平均每年喝掉165杯茶，你从小就是品茶大师",
        "life_expectancy": "82岁",
        "probability_note": "全球约0.5%的婴儿",
        "famous_for": ["大本钟", "哈利波特", "披头士", "温布尔登"]
    },
    {
        "country": "韩国",
        "country_en": "South Korea",
        "flag": "🇰🇷",
        "continent": "亚洲",
        "region": "东亚",
        "births": 240,
        "coordinates": {"lat": 35.9078, "lng": 127.7669},
        "color": "#CD2E3A",
        "description": "🎤 K-POP和泡菜的故乡，网速快到让你怀疑人生，卷的程度堪比中国",
        "lifestyle": "凌晨3点还在PC房打游戏，周末补习班排满。但至少你有全世界最好的网速和最辣的炸鸡",
        "traits": ["电竞强国", "K-POP", "美妆大国", "5G先驱", "泡菜文化"],
        "fun_fact": "💡 韩国的平均网速是全球第一，下载电影只需几秒钟",
        "life_expectancy": "84岁",
        "probability_note": "全球约0.17%的婴儿",
        "famous_for": ["K-POP", "电竞", "美妆", "泡菜"]
    },
    {
        "country": "澳大利亚",
        "country_en": "Australia",
        "flag": "🇦🇺",
        "continent": "大洋洲",
        "region": "大洋洲",
        "births": 310,
        "coordinates": {"lat": -25.2744, "lng": 133.7751},
        "color": "#012169",
        "description": "🦘 袋鼠比人多的国度，冲浪和烧烤是生活方式。蜘蛛、蛇、鳄鱼是日常邻居",
        "lifestyle": "早上冲浪，中午BBQ，晚上海滩看日落。所有生物都想杀死你，但至少风景很美",
        "traits": ["冲浪天堂", "袋鼠王国", "矿产大国", "多元文化", "阳光海滩"],
        "fun_fact": "💡 澳大利亚有超过1万个海滩，你可以每天去不同的海滩27年",
        "life_expectancy": "83岁",
        "probability_note": "全球约0.22%的新生儿",
        "famous_for": ["大堡礁", "悉尼歌剧院", "袋鼠", "冲浪"]
    },
    {
        "country": "加拿大",
        "country_en": "Canada",
        "flag": "🇨🇦",
        "continent": "北美洲",
        "region": "北美",
        "births": 380,
        "coordinates": {"lat": 56.1304, "lng": -106.3468},
        "color": "#FF0000",
        "description": "🍁 枫叶之国，冰球比足球重要，说'Sorry'是国民习惯，礼貌刻在基因里",
        "lifestyle": "冬天零下30度也要出门铲雪，夏天穿短袖15度就算热。全民都会说Sorry",
        "traits": ["枫叶之国", "冰球王国", "多元文化", "自然美景", "礼貌天堂"],
        "fun_fact": "💡 加拿大的森林覆盖率达38.7%，你从小就能拥抱大自然",
        "life_expectancy": "82岁",
        "probability_note": "全球约0.27%的婴儿",
        "famous_for": ["枫叶", "冰球", "尼亚加拉瀑布", "极光"]
    },
    {
        "country": "法国",
        "country_en": "France",
        "flag": "🇫🇷",
        "continent": "欧洲",
        "region": "西欧",
        "births": 680,
        "coordinates": {"lat": 46.2276, "lng": 2.2137},
        "color": "#0055A4",
        "description": "🥐 浪漫之都，红酒、奶酪和埃菲尔铁塔是你的日常。慢节奏生活是一种艺术",
        "lifestyle": "早餐吃可颂配咖啡，午餐2小时起步，下午4点下班去咖啡馆。罢工是全民运动",
        "traits": ["浪漫之国", "美食天堂", "时尚之都", "艺术殿堂", "红酒文化"],
        "fun_fact": "💡 法国有超过400种奶酪，你可以每天吃不同的奶酪一整年",
        "life_expectancy": "83岁",
        "probability_note": "全球约0.49%的新生儿",
        "famous_for": ["埃菲尔铁塔", "卢浮宫", "红酒", "时尚"]
    },
    {
        "country": "墨西哥",
        "country_en": "Mexico",
        "flag": "🇲🇽",
        "continent": "北美洲",
        "region": "中美",
        "births": 2000,
        "coordinates": {"lat": 23.6345, "lng": -102.5528},
        "color": "#006847",
        "description": "🌮 玉米饼和龙舌兰的故乡，亡灵节比春节还热闹，玛雅文明是你的骄傲",
        "lifestyle": "塔可是主食，辣椒是标配，龙舌兰是社交货币。亡灵节时全家聚会纪念祖先",
        "traits": ["美食天堂", "玛雅文明", "龙舌兰", "亡灵节", "热情奔放"],
        "fun_fact": "💡 墨西哥是巧克力的发源地，这里的人发明了热可可",
        "life_expectancy": "75岁",
        "probability_note": "全球约1.4%的新生儿",
        "famous_for": ["玛雅金字塔", "龙舌兰", "亡灵节", "塔可"]
    },
    {
        "country": "俄罗斯",
        "country_en": "Russia",
        "flag": "🇷🇺",
        "continent": "欧洲/亚洲",
        "region": "东欧",
        "births": 1400,
        "coordinates": {"lat": 61.5240, "lng": 105.3188},
        "color": "#0039A6",
        "description": "❄️ 世界上最大的国家，横跨11个时区。伏特加、套娃和战斗民族的传说",
        "lifestyle": "零下40度短袖出门，伏特加当水喝。森林面积比亚马逊还大，棕熊可能是你的邻居",
        "traits": ["战斗民族", "广袤领土", "太空强国", "文学艺术", "伏特加文化"],
        "fun_fact": "💡 俄罗斯的森林面积比亚马逊还大，你天生就是森林之子",
        "life_expectancy": "73岁",
        "probability_note": "全球约1%的婴儿",
        "famous_for": ["克里姆林宫", "芭蕾舞", "太空站", "伏特加"]
    },
    {
        "country": "埃及",
        "country_en": "Egypt",
        "flag": "🇪🇬",
        "continent": "非洲",
        "region": "北非",
        "births": 2500,
        "coordinates": {"lat": 26.8206, "lng": 30.8025},
        "color": "#CE1126",
        "description": "🏺 金字塔的守护者，五千年文明就在你家门口。尼罗河是生命之源",
        "lifestyle": "在金字塔脚下吃早餐，在博物馆里找祖先的文物。每个石头都有五千年历史",
        "traits": ["古文明", "金字塔", "尼罗河", "历史宝库", "神秘文化"],
        "fun_fact": "💡 埃及有138座金字塔，你的祖先可能建造过它们",
        "life_expectancy": "72岁",
        "probability_note": "全球约1.8%的婴儿",
        "famous_for": ["金字塔", "狮身人面像", "法老", "尼罗河"]
    },
    {
        "country": "南非",
        "country_en": "South Africa",
        "flag": "🇿🇦",
        "continent": "非洲",
        "region": "南非",
        "births": 1100,
        "coordinates": {"lat": -30.5595, "lng": 22.9375},
        "color": "#007A4D",
        "description": "🦁 彩虹之国，11种官方语言让你天生语言天才。看野生动物不用去动物园",
        "lifestyle": "早上看狮子，中午看大象，晚上BBQ。三个首都让你不知道该去哪里办身份证",
        "traits": ["彩虹之国", "野生动物", "钻石之国", "多元文化", "自然奇观"],
        "fun_fact": "💡 南非有三个首都，一出生就拥有三个家乡",
        "life_expectancy": "64岁",
        "probability_note": "全球约0.79%的婴儿",
        "famous_for": ["克鲁格国家公园", "好望角", "钻石", "野生动物"]
    },
    {
        "country": "越南",
        "country_en": "Vietnam",
        "flag": "🇻🇳",
        "continent": "亚洲",
        "region": "东南亚",
        "births": 1400,
        "coordinates": {"lat": 14.0583, "lng": 108.2772},
        "color": "#DA251D",
        "description": "🍜 河粉和咖啡的天堂，摩托车大军堪称世界奇观。滴漏咖啡是生活节奏",
        "lifestyle": "早上一碗河粉，上班骑摩托车在万军丛中穿梭。咖啡要慢慢滴，人生不能着急",
        "traits": ["河粉之国", "咖啡文化", "摩托车王国", "美丽海滩", "历史悠久"],
        "fun_fact": "💡 越南是世界第二大咖啡出口国，你天生就是咖啡鉴赏家",
        "life_expectancy": "76岁",
        "probability_note": "全球约1%的新生儿",
        "famous_for": ["河粉", "下龙湾", "滴漏咖啡", "会安古城"]
    },
    {
        "country": "阿根廷",
        "country_en": "Argentina",
        "flag": "🇦🇷",
        "continent": "南美洲",
        "region": "南美",
        "births": 650,
        "coordinates": {"lat": -38.4161, "lng": -63.6167},
        "color": "#75AADB",
        "description": "⚽ 探戈和梅西的故乡，牛排大到一个人吃不完。足球是宗教，探戈是灵魂",
        "lifestyle": "晚餐10点才开始，午夜跳探戈，凌晨讨论足球。牛排每顿必须有",
        "traits": ["足球强国", "探戈发源地", "牛排天堂", "巴塔哥尼亚", "冰川奇景"],
        "fun_fact": "💡 阿根廷人均牛肉消费量世界第一，天生肉食动物",
        "life_expectancy": "77岁",
        "probability_note": "全球约0.46%的新生儿",
        "famous_for": ["梅西", "探戈", "牛排", "伊瓜苏瀑布"]
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
