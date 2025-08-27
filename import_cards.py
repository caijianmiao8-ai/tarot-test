import json
import pymysql

# 配置信息 - 替换为您的实际信息
config = {
    "host": "ruoshui233.mysql.pythonanywhere-services.com",
    "user": "ruoshui233",
    "password": "cai-6831",  # 替换为数据库密码
    "db": "ruoshui233$tarot",
    "charset": "utf8mb4"
}

# 文件路径 - 替换为实际JSON路径
JSON_PATH = "/home/ruoshui233/tarot-app/tarot_cards.json"

def import_data():
    try:
        # 读取JSON数据
        with open(JSON_PATH, "r", encoding="utf-8") as f:
            cards = json.load(f)
        
        # 连接数据库
        conn = pymysql.connect(**config)
        cursor = conn.cursor()
        
        # 检查表是否存在
        cursor.execute("SHOW TABLES LIKE 'cards'")
        table_exists = cursor.fetchone()
        
        if not table_exists:
            # 创建cards表
            create_table_sql = """
            CREATE TABLE cards (
                id INT PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                image VARCHAR(255),
                meaning_up TEXT,
                meaning_rev TEXT,
                guidance TEXT
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """
            cursor.execute(create_table_sql)
            print("✅ 成功创建 cards 表")
        
        # 导入每张卡牌
        success_count = 0
        for card in cards:
            sql = """
            REPLACE INTO cards 
            (id, name, image, meaning_up, meaning_rev, guidance)
            VALUES (%s, %s, %s, %s, %s, %s)
            """
            cursor.execute(sql, (
                card["id"],
                card["name"],
                card["image"],
                card["meaning_up"],
                card["meaning_rev"],
                card["guidance"]
            ))
            success_count += 1
        
        conn.commit()
        print(f"✅ 成功导入 {success_count}/{len(cards)} 张卡牌")
        
    except Exception as e:
        print(f"❌ 导入失败: {str(e)}")
        if 'conn' in locals(): 
            conn.rollback()
        
    finally:
        if 'conn' in locals(): 
            conn.close()

if __name__ == "__main__":
    import_data()