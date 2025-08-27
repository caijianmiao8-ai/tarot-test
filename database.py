# database.py
import sqlite3
import json

def init_database():
    # 连接数据库（不存在则创建）
    conn = sqlite3.connect('tarot.db')
    cursor = conn.cursor()
    
    # 创建抽牌记录表
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS readings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        card_id INTEGER NOT NULL,
        direction TEXT NOT NULL,
        date TEXT NOT NULL
    )
    ''')
    
    # 创建塔罗牌数据表
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS tarot_cards (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        image TEXT,
        meaning_up TEXT NOT NULL,
        meaning_rev TEXT NOT NULL,
        guidance TEXT NOT NULL
    )
    ''')
    
    # 检查卡片数据是否已存在
    cursor.execute("SELECT COUNT(*) FROM tarot_cards")
    if cursor.fetchone()[0] == 0:
        # 加载预置卡片数据
        with open('data/tarot_cards.json', 'r', encoding='utf-8') as f:
            cards = json.load(f)
            
        # 插入卡片数据
        for card in cards:
            cursor.execute('''
            INSERT INTO tarot_cards (id, name, image, meaning_up, meaning_rev, guidance)
            VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                card['id'],
                card['name'],
                card.get('image', ''),
                card['meaning_up'],
                card['meaning_rev'],
                card['guidance']
            ))
    
    conn.commit()
    conn.close()

if __name__ == '__main__':
    init_database()
    print("数据库初始化完成！")