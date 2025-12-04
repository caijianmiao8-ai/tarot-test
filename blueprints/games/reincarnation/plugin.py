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
    },
    {
        "country": "泰国",
        "country_en": "Thailand",
        "flag": "🇹🇭",
        "continent": "亚洲",
        "region": "东南亚",
        "births": 700,
        "coordinates": {"lat": 15.8700, "lng": 100.9925},
        "color": "#A51931",
        "description": "🙏 微笑之国，寺庙、海滩和泰式按摩是标配。冬阴功和芒果糯米饭是灵魂食物",
        "lifestyle": "早上拜佛，中午吃街边小吃，下午去海滩，晚上夜市淘宝。每天对陌生人微笑100次",
        "traits": ["微笑之国", "佛教文化", "海滩天堂", "泰拳", "街头美食"],
        "fun_fact": "💡 泰国有超过4万座寺庙，你可能每周去不同的寺庙还要80年",
        "life_expectancy": "77岁",
        "probability_note": "全球约0.5%的新生儿",
        "famous_for": ["大皇宫", "普吉岛", "泰式按摩", "冬阴功汤"]
    },
    {
        "country": "菲律宾",
        "country_en": "Philippines",
        "flag": "🇵🇭",
        "continent": "亚洲",
        "region": "东南亚",
        "births": 2400,
        "coordinates": {"lat": 12.8797, "lng": 121.7740},
        "color": "#0038A8",
        "description": "🏝️ 七千多个岛屿组成的群岛国家，每天都能去不同的海滩。天生乐观开朗",
        "lifestyle": "早上跳岛游，中午吃烤乳猪，晚上唱卡拉OK。台风来了也要笑着面对",
        "traits": ["千岛之国", "热情好客", "卡拉OK文化", "潜水天堂", "烤乳猪"],
        "fun_fact": "💡 菲律宾人是世界上最爱唱卡拉OK的民族，你天生就是麦霸",
        "life_expectancy": "71岁",
        "probability_note": "全球约1.7%的新生儿",
        "famous_for": ["长滩岛", "巴拉望", "烤乳猪", "珍珠"]
    },
    {
        "country": "孟加拉国",
        "country_en": "Bangladesh",
        "flag": "🇧🇩",
        "continent": "亚洲",
        "region": "南亚",
        "births": 3000,
        "coordinates": {"lat": 23.6850, "lng": 90.3563},
        "color": "#006A4E",
        "description": "🌾 世界上人口密度最高的国家之一，恒河三角洲孕育了丰富的文化",
        "lifestyle": "在水乡泽国中长大，雨季是日常。米饭和咖喱鱼是每天标配",
        "traits": ["人口密集", "纺织大国", "河流之国", "咖喱文化", "板球热爱"],
        "fun_fact": "💡 孟加拉国是世界第二大成衣出口国，你穿的T恤可能就是这里制造的",
        "life_expectancy": "73岁",
        "probability_note": "全球约2.1%的新生儿",
        "famous_for": ["孟加拉虎", "红树林", "纺织业", "恒河三角洲"]
    },
    {
        "country": "土耳其",
        "country_en": "Turkey",
        "flag": "🇹🇷",
        "continent": "欧洲/亚洲",
        "region": "西亚",
        "births": 1200,
        "coordinates": {"lat": 38.9637, "lng": 35.2433},
        "color": "#E30A17",
        "description": "🕌 横跨欧亚的文明十字路口，东西方文化在这里碰撞。烤肉和红茶是生活必需品",
        "lifestyle": "早餐吃橄榄配奶酪，喝红茶不喝咖啡。逛大巴扎砍价是必备技能",
        "traits": ["欧亚桥梁", "烤肉王国", "历史古迹", "温泉之国", "红茶文化"],
        "fun_fact": "💡 土耳其人均每年喝掉3公斤茶叶，比英国人还能喝茶",
        "life_expectancy": "78岁",
        "probability_note": "全球约0.86%的新生儿",
        "famous_for": ["圣索菲亚大教堂", "卡帕多奇亚", "土耳其烤肉", "棉花堡"]
    },
    {
        "country": "伊朗",
        "country_en": "Iran",
        "flag": "🇮🇷",
        "continent": "亚洲",
        "region": "西亚",
        "births": 1300,
        "coordinates": {"lat": 32.4279, "lng": 53.6880},
        "color": "#239F40",
        "description": "🏛️ 波斯帝国的继承者，两千五百年历史的古文明。诗歌和地毯是文化符号",
        "lifestyle": "喝藏红花茶，吃烤羊肉串，读鲁米的诗。波斯地毯编织是家传技艺",
        "traits": ["古文明", "石油大国", "地毯王国", "诗歌文化", "藏红花"],
        "fun_fact": "💡 伊朗生产全球90%以上的藏红花，这是世界上最贵的香料",
        "life_expectancy": "77岁",
        "probability_note": "全球约0.93%的新生儿",
        "famous_for": ["波斯波利斯", "伊斯法罕", "波斯地毯", "藏红花"]
    },
    {
        "country": "马来西亚",
        "country_en": "Malaysia",
        "flag": "🇲🇾",
        "continent": "亚洲",
        "region": "东南亚",
        "births": 500,
        "coordinates": {"lat": 4.2105, "lng": 101.9758},
        "color": "#CC0001",
        "description": "🌴 多元文化的热带天堂，马来、华人、印度文化完美融合。美食是最大优势",
        "lifestyle": "早餐吃椰浆饭，午餐吃肉骨茶，晚餐吃沙爹。三种族三种语言三种美食",
        "traits": ["多元文化", "热带雨林", "双峰塔", "美食天堂", "橡胶大国"],
        "fun_fact": "💡 马来西亚的吉隆坡双峰塔曾是世界最高建筑，现在仍是双塔中最高的",
        "life_expectancy": "76岁",
        "probability_note": "全球约0.36%的新生儿",
        "famous_for": ["双峰塔", "槟城美食", "热带雨林", "榴莲"]
    },
    {
        "country": "意大利",
        "country_en": "Italy",
        "flag": "🇮🇹",
        "continent": "欧洲",
        "region": "南欧",
        "births": 420,
        "coordinates": {"lat": 41.8719, "lng": 12.5674},
        "color": "#009246",
        "description": "🍕 文艺复兴的摇篮，披萨和意面的故乡。慢生活是一种哲学",
        "lifestyle": "早上喝浓缩咖啡，午餐2小时，下午小睡，晚上10点才吃晚餐。手势比话还多",
        "traits": ["文艺复兴", "美食王国", "时尚之都", "艺术宝库", "足球强国"],
        "fun_fact": "💡 意大利有超过450种面食，你可以每天吃不同的意面一年多",
        "life_expectancy": "84岁",
        "probability_note": "全球约0.3%的新生儿",
        "famous_for": ["罗马斗兽场", "比萨斜塔", "威尼斯", "披萨"]
    },
    {
        "country": "西班牙",
        "country_en": "Spain",
        "flag": "🇪🇸",
        "continent": "欧洲",
        "region": "南欧",
        "births": 340,
        "coordinates": {"lat": 40.4637, "lng": -3.7492},
        "color": "#AA151B",
        "description": "💃 弗拉明戈和斗牛的国度，午睡是神圣不可侵犯的。晚餐10点才开始",
        "lifestyle": "早上10点才开始工作，下午2点午睡，晚上10点吃晚餐，午夜还在街上闲逛",
        "traits": ["弗拉明戈", "斗牛", "午睡文化", "足球劲旅", "海鲜饭"],
        "fun_fact": "💡 西班牙人的晚餐时间是全欧洲最晚的，通常在晚上9-10点",
        "life_expectancy": "84岁",
        "probability_note": "全球约0.24%的新生儿",
        "famous_for": ["圣家堂", "阿尔罕布拉宫", "斗牛", "海鲜饭"]
    },
    {
        "country": "波兰",
        "country_en": "Poland",
        "flag": "🇵🇱",
        "continent": "欧洲",
        "region": "东欧",
        "births": 350,
        "coordinates": {"lat": 51.9194, "lng": 19.1451},
        "color": "#DC143C",
        "description": "🏰 中欧的十字路口，肖邦的故乡。饺子和伏特加是国民美食",
        "lifestyle": "周日必须去教堂，波兰饺子配伏特加。肖邦的钢琴曲是从小的BGM",
        "traits": ["音乐之国", "历史名城", "伏特加", "宗教虔诚", "琥珀之国"],
        "fun_fact": "💡 波兰出产全球70%的琥珀，你可能从小就在琥珀堆里长大",
        "life_expectancy": "79岁",
        "probability_note": "全球约0.25%的新生儿",
        "famous_for": ["肖邦", "奥斯维辛", "华沙老城", "琥珀"]
    },
    {
        "country": "荷兰",
        "country_en": "Netherlands",
        "flag": "🇳🇱",
        "continent": "欧洲",
        "region": "西欧",
        "births": 160,
        "coordinates": {"lat": 52.1326, "lng": 5.2913},
        "color": "#21468B",
        "description": "🚲 风车和郁金香的国度，自行车比人还多。低于海平面也能过得很滋润",
        "lifestyle": "骑车上班上学购物，一天骑行20公里是常态。奶酪和煎饼是主食",
        "traits": ["自行车王国", "郁金香", "风车", "低地之国", "奶酪大国"],
        "fun_fact": "💡 荷兰有超过2300万辆自行车，比全国人口还多",
        "life_expectancy": "82岁",
        "probability_note": "全球约0.11%的新生儿",
        "famous_for": ["风车村", "郁金香花海", "阿姆斯特丹运河", "梵高"]
    },
    {
        "country": "瑞典",
        "country_en": "Sweden",
        "flag": "🇸🇪",
        "continent": "欧洲",
        "region": "北欧",
        "births": 110,
        "coordinates": {"lat": 60.1282, "lng": 18.6435},
        "color": "#006AA7",
        "description": "❄️ 北欧福利天堂，极光和宜家的故乡。冬天黑夜漫长，但咖啡和肉桂卷让人温暖",
        "lifestyle": "夏天日不落，冬天不见太阳。喝咖啡是国民运动，组装宜家家具是必备技能",
        "traits": ["福利国家", "宜家", "诺贝尔奖", "极光", "设计之国"],
        "fun_fact": "💡 瑞典人均咖啡消费量世界第二，每天至少3-4杯",
        "life_expectancy": "83岁",
        "probability_note": "全球约0.08%的新生儿",
        "famous_for": ["宜家", "诺贝尔奖", "极光", "肉桂卷"]
    },
    {
        "country": "埃塞俄比亚",
        "country_en": "Ethiopia",
        "flag": "🇪🇹",
        "continent": "非洲",
        "region": "东非",
        "births": 3100,
        "coordinates": {"lat": 9.1450, "lng": 40.4897},
        "color": "#078930",
        "description": "☕ 咖啡的发源地，人类文明的摇篮之一。高原山地孕育了独特文化",
        "lifestyle": "每天三次咖啡仪式，吃英吉拉配各种酱料。东非大裂谷就在家门口",
        "traits": ["咖啡发源地", "古文明", "长跑王国", "高原之国", "独特文字"],
        "fun_fact": "💡 咖啡(Coffee)这个词就来源于埃塞俄比亚的卡法(Kaffa)地区",
        "life_expectancy": "67岁",
        "probability_note": "全球约2.2%的新生儿",
        "famous_for": ["咖啡仪式", "拉利贝拉岩石教堂", "长跑", "东非大裂谷"]
    },
    {
        "country": "刚果(金)",
        "country_en": "DR Congo",
        "flag": "🇨🇩",
        "continent": "非洲",
        "region": "中非",
        "births": 3500,
        "coordinates": {"lat": -4.0383, "lng": 21.7587},
        "color": "#007FFF",
        "description": "🌳 拥有世界第二大热带雨林，刚果河养育着这片土地。矿产资源极其丰富",
        "lifestyle": "在热带雨林边缘长大，大猩猩可能是邻居。音乐和舞蹈是日常",
        "traits": ["雨林王国", "矿产宝库", "音乐文化", "刚果河", "生物多样性"],
        "fun_fact": "💡 刚果盆地热带雨林仅次于亚马逊，被称为地球的第二个肺",
        "life_expectancy": "61岁",
        "probability_note": "全球约2.5%的新生儿",
        "famous_for": ["刚果河", "热带雨林", "钴矿", "山地大猩猩"]
    },
    {
        "country": "坦桑尼亚",
        "country_en": "Tanzania",
        "flag": "🇹🇿",
        "continent": "非洲",
        "region": "东非",
        "births": 2000,
        "coordinates": {"lat": -6.3690, "lng": 34.8888},
        "color": "#1EB53A",
        "description": "🦁 塞伦盖蒂的动物大迁徙，乞力马扎罗的雪。野生动物和你一起长大",
        "lifestyle": "看狮子、大象是日常。爬非洲最高峰乞力马扎罗是人生目标",
        "traits": ["野生动物天堂", "乞力马扎罗", "塞伦盖蒂", "桑给巴尔", "大迁徙"],
        "fun_fact": "💡 每年的角马大迁徙涉及超过150万只动物，是地球上最壮观的自然景观",
        "life_expectancy": "66岁",
        "probability_note": "全球约1.4%的新生儿",
        "famous_for": ["塞伦盖蒂", "乞力马扎罗", "桑给巴尔岛", "动物大迁徙"]
    },
    {
        "country": "肯尼亚",
        "country_en": "Kenya",
        "flag": "🇰🇪",
        "continent": "非洲",
        "region": "东非",
        "births": 1400,
        "coordinates": {"lat": -0.0236, "lng": 37.9062},
        "color": "#BB0000",
        "description": "🏃 马拉松王国，长跑冠军的摇篮。马赛马拉的野生动物和马赛人的文化",
        "lifestyle": "从小在高原奔跑，跑步是通勤方式。看野生动物不用去动物园",
        "traits": ["长跑王国", "野生动物", "马赛文化", "东非明珠", "咖啡产地"],
        "fun_fact": "💡 肯尼亚长跑运动员几乎垄断了世界马拉松比赛的冠军",
        "life_expectancy": "67岁",
        "probability_note": "全球约1%的新生儿",
        "famous_for": ["马拉松", "马赛马拉", "东非大裂谷", "肯尼亚咖啡"]
    },
    {
        "country": "哥伦比亚",
        "country_en": "Colombia",
        "flag": "🇨🇴",
        "continent": "南美洲",
        "region": "南美",
        "births": 650,
        "coordinates": {"lat": 4.5709, "lng": -74.2973},
        "color": "#FCD116",
        "description": "☕ 世界上最好的咖啡产地之一，加勒比海和太平洋的双面海景",
        "lifestyle": "早上喝世界最好的咖啡，听Salsa音乐，下午去海滩。翡翠和咖啡是骄傲",
        "traits": ["咖啡王国", "翡翠之国", "Salsa音乐", "双海之国", "热情奔放"],
        "fun_fact": "💡 哥伦比亚出产全球70%以上的翡翠，质量世界第一",
        "life_expectancy": "78岁",
        "probability_note": "全球约0.46%的新生儿",
        "famous_for": ["哥伦比亚咖啡", "翡翠", "卡塔赫纳", "黄金博物馆"]
    },
    {
        "country": "智利",
        "country_en": "Chile",
        "flag": "🇨🇱",
        "continent": "南美洲",
        "region": "南美",
        "births": 220,
        "coordinates": {"lat": -35.6751, "lng": -71.543},
        "color": "#0039A6",
        "description": "🗻 世界上最狭长的国家，从沙漠到冰川应有尽有。红酒和海鲜是绝配",
        "lifestyle": "北部沙漠，中部地中海气候，南部冰川。一个国家体验四季和所有地形",
        "traits": ["狭长国家", "红酒大国", "铜矿王国", "复活节岛", "地形多样"],
        "fun_fact": "💡 智利南北长4300公里，但东西最窄处只有90公里",
        "life_expectancy": "80岁",
        "probability_note": "全球约0.16%的新生儿",
        "famous_for": ["复活节岛", "阿塔卡马沙漠", "红酒", "铜矿"]
    },
    {
        "country": "秘鲁",
        "country_en": "Peru",
        "flag": "🇵🇪",
        "continent": "南美洲",
        "region": "南美",
        "births": 530,
        "coordinates": {"lat": -9.1900, "lng": -75.0152},
        "color": "#D91023",
        "description": "🏔️ 印加文明的继承者，马丘比丘是你家的后花园。羊驼比汽车常见",
        "lifestyle": "吃quinoa藜麦，看羊驼，爬马丘比丘。印加文明的遗迹遍地都是",
        "traits": ["印加文明", "马丘比丘", "羊驼王国", "美食天堂", "亚马逊雨林"],
        "fun_fact": "💡 秘鲁有超过3000种土豆品种，是土豆的发源地",
        "life_expectancy": "77岁",
        "probability_note": "全球约0.38%的新生儿",
        "famous_for": ["马丘比丘", "纳斯卡线条", "的的喀喀湖", "羊驼"]
    },
    {
        "country": "新西兰",
        "country_en": "New Zealand",
        "flag": "🇳🇿",
        "continent": "大洋洲",
        "region": "大洋洲",
        "births": 60,
        "coordinates": {"lat": -40.9006, "lng": 174.886},
        "color": "#00247D",
        "description": "🥝 中土世界的现实版，绵羊比人多5倍。极限运动的天堂",
        "lifestyle": "早上蹦极，中午跳伞，下午漂流，晚上看《指环王》取景地。羊是真正的居民",
        "traits": ["中土世界", "极限运动", "绵羊王国", "纯净自然", "毛利文化"],
        "fun_fact": "💡 新西兰有超过2800万只羊，人均拥有5只羊",
        "life_expectancy": "82岁",
        "probability_note": "全球约0.04%的新生儿",
        "famous_for": ["指环王", "蹦极", "霍比特村", "峡湾"]
    },
    {
        "country": "沙特阿拉伯",
        "country_en": "Saudi Arabia",
        "flag": "🇸🇦",
        "continent": "亚洲",
        "region": "西亚",
        "births": 550,
        "coordinates": {"lat": 23.8859, "lng": 45.0792},
        "color": "#165B33",
        "description": "🕋 伊斯兰圣地麦加和麦地那，石油王国。沙漠中建起的现代奇迹",
        "lifestyle": "在空调房里躲避50度高温，开豪车是基本配置。一年有2个月要斋戒",
        "traits": ["石油王国", "伊斯兰圣地", "沙漠之国", "豪车天堂", "现代化进程"],
        "fun_fact": "💡 沙特拥有世界25%的已探明石油储量，你可能从小就是石油大亨",
        "life_expectancy": "76岁",
        "probability_note": "全球约0.39%的新生儿",
        "famous_for": ["麦加", "石油", "沙漠", "未来新城"]
    },
    {
        "country": "阿联酋",
        "country_en": "UAE",
        "flag": "🇦🇪",
        "continent": "亚洲",
        "region": "西亚",
        "births": 120,
        "coordinates": {"lat": 23.4241, "lng": 53.8478},
        "color": "#00732F",
        "description": "🏙️ 沙漠中的奇迹之城，迪拜塔和人工岛。从贫瘠沙漠到未来都市只用了50年",
        "lifestyle": "在世界最高楼俯瞰沙漠，去人工岛的七星酒店喝下午茶。夏天室外50度但室内零下",
        "traits": ["未来之城", "奢华生活", "世界之最", "免税天堂", "人工奇迹"],
        "fun_fact": "💡 迪拜拥有世界最高建筑、最大购物中心、最大人工岛等无数世界之最",
        "life_expectancy": "78岁",
        "probability_note": "全球约0.09%的新生儿",
        "famous_for": ["哈利法塔", "棕榈岛", "帆船酒店", "迪拜购物中心"]
    },
    {
        "country": "新加坡",
        "country_en": "Singapore",
        "flag": "🇸🇬",
        "continent": "亚洲",
        "region": "东南亚",
        "births": 35,
        "coordinates": {"lat": 1.3521, "lng": 103.8198},
        "color": "#ED2939",
        "description": "🦁 花园城市国家，从渔村到金融中心只用了60年。干净整洁到极致",
        "lifestyle": "在购物中心度过大半时间，嚼口香糖要罚款。多元美食让你每天吃不重样",
        "traits": ["花园城市", "金融中心", "多元文化", "美食天堂", "高效有序"],
        "fun_fact": "💡 新加坡是世界上罚款种类最多的国家，连喂鸽子都要罚款",
        "life_expectancy": "84岁",
        "probability_note": "全球约0.025%的新生儿",
        "famous_for": ["鱼尾狮", "滨海湾花园", "肉骨茶", "牛车水"]
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
