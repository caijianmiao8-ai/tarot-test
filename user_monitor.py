#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
用户系统监控脚本
运行: python user_monitor.py
"""

import pymysql
from datetime import datetime, timedelta
import time

# 数据库配置
DB_CONFIG = {
    "host": "ruoshui233.mysql.pythonanywhere-services.com",
    "user": "ruoshui233",
    "password": "cai-6831", 
    "database": "ruoshui233$tarot",
    "charset": "utf8mb4"
}

def get_connection():
    return pymysql.connect(**DB_CONFIG, cursorclass=pymysql.cursors.DictCursor)

def monitor_users():
    """监控用户活动"""
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            print("=" * 60)
            print(f"🔮 塔罗牌应用用户监控 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print("=" * 60)
            
            # 基础统计
            cursor.execute("SELECT COUNT(*) as total FROM users")
            total_users = cursor.fetchone()['total']
            
            cursor.execute("SELECT COUNT(*) as total FROM readings")
            total_readings = cursor.fetchone()['total']
            
            print(f"📊 基础统计:")
            print(f"   总用户数: {total_users}")
            print(f"   总抽牌记录: {total_readings}")
            if total_users > 0:
                print(f"   平均每用户抽牌: {total_readings/total_users:.1f} 次")
            
            # 时间范围统计
            print(f"\n📅 时间统计:")
            
            # 今日统计
            cursor.execute("SELECT COUNT(*) as count FROM users WHERE DATE(first_visit) = CURDATE()")
            new_today = cursor.fetchone()['count']
            
            cursor.execute("SELECT COUNT(*) as count FROM users WHERE DATE(last_visit) = CURDATE()")
            active_today = cursor.fetchone()['count']
            
            cursor.execute("SELECT COUNT(*) as count FROM readings WHERE DATE(date) = CURDATE()")
            readings_today = cursor.fetchone()['count']
            
            print(f"   今日新用户: {new_today}")
            print(f"   今日活跃用户: {active_today}")
            print(f"   今日抽牌: {readings_today}")
            
            # 本周统计
            cursor.execute("SELECT COUNT(*) as count FROM users WHERE first_visit >= DATE_SUB(CURDATE(), INTERVAL 7 DAY)")
            new_week = cursor.fetchone()['count']
            
            cursor.execute("SELECT COUNT(*) as count FROM users WHERE last_visit >= DATE_SUB(CURDATE(), INTERVAL 7 DAY)")
            active_week = cursor.fetchone()['count']
            
            print(f"   本周新用户: {new_week}")
            print(f"   本周活跃用户: {active_week}")
            
            # 用户活跃度分析
            print(f"\n👥 用户活跃度:")
            
            cursor.execute("""
                SELECT 
                    CASE 
                        WHEN visit_count = 1 THEN '仅访问1次'
                        WHEN visit_count BETWEEN 2 AND 5 THEN '访问2-5次'
                        WHEN visit_count BETWEEN 6 AND 10 THEN '访问6-10次'
                        WHEN visit_count > 10 THEN '访问10次以上'
                    END as visit_range,
                    COUNT(*) as user_count
                FROM users 
                GROUP BY 
                    CASE 
                        WHEN visit_count = 1 THEN '仅访问1次'
                        WHEN visit_count BETWEEN 2 AND 5 THEN '访问2-5次'
                        WHEN visit_count BETWEEN 6 AND 10 THEN '访问6-10次'
                        WHEN visit_count > 10 THEN '访问10次以上'
                    END
                ORDER BY user_count DESC
            """)
            visit_stats = cursor.fetchall()
            
            for stat in visit_stats:
                print(f"   {stat['visit_range']}: {stat['user_count']} 用户")
            
            # 最近活跃用户
            print(f"\n🔥 最近活跃用户:")
            cursor.execute("""
                SELECT u.id, u.device_id, u.last_visit, u.visit_count,
                       COUNT(r.id) as total_readings
                FROM users u 
                LEFT JOIN readings r ON u.id = r.user_id 
                WHERE u.last_visit >= DATE_SUB(NOW(), INTERVAL 24 HOUR)
                GROUP BY u.id 
                ORDER BY u.last_visit DESC 
                LIMIT 10
            """)
            recent_active = cursor.fetchall()
            
            if recent_active:
                for user in recent_active:
                    last_visit = user['last_visit'].strftime('%H:%M:%S') if user['last_visit'] else 'N/A'
                    print(f"   用户 {user['id'][:8]}... | 最后访问: {last_visit} | 访问{user['visit_count']}次 | 抽牌{user['total_readings']}次")
            else:
                print("   过去24小时内没有活跃用户")
            
            # 数据质量检查
            print(f"\n🔍 数据质量检查:")
            
            # 检查孤儿记录
            cursor.execute("""
                SELECT COUNT(*) as orphaned 
                FROM readings r 
                LEFT JOIN users u ON r.user_id = u.id 
                WHERE u.id IS NULL
            """)
            orphaned = cursor.fetchone()['orphaned']
            
            if orphaned > 0:
                print(f"   ❌ 发现 {orphaned} 条孤儿记录")
            else:
                print(f"   ✅ 数据完整性良好，无孤儿记录")
            
            # 检查访问计数准确性（抽样检查）
            cursor.execute("""
                SELECT u.id, u.visit_count, COUNT(DISTINCT DATE(r.timestamp)) as actual_days
                FROM users u
                LEFT JOIN readings r ON u.id = r.user_id
                GROUP BY u.id
                HAVING actual_days > 0 AND u.visit_count < actual_days
                LIMIT 5
            """)
            inconsistent = cursor.fetchall()
            
            if inconsistent:
                print(f"   ⚠️ 发现 {len(inconsistent)} 个用户的访问计数可能不准确")
            else:
                print(f"   ✅ 用户访问计数正常")
            
            # 设备指纹重复检查
            cursor.execute("""
                SELECT device_id, COUNT(*) as user_count
                FROM users 
                GROUP BY device_id 
                HAVING COUNT(*) > 1
                ORDER BY user_count DESC
                LIMIT 5
            """)
            duplicate_devices = cursor.fetchall()
            
            if duplicate_devices:
                print(f"   ⚠️ 发现设备指纹重复:")
                for dup in duplicate_devices:
                    print(f"      设备 {dup['device_id'][:20]}... 有 {dup['user_count']} 个用户")
            else:
                print(f"   ✅ 设备指纹唯一性良好")
                
    except Exception as e:
        print(f"❌ 监控过程出错: {e}")
    finally:
        conn.close()

def detailed_user_analysis():
    """详细用户分析"""
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            print("\n" + "=" * 60)
            print("📈 详细用户分析")
            print("=" * 60)
            
            # 用户生命周期分析
            print("🔄 用户留存分析:")
            cursor.execute("""
                SELECT 
                    DATEDIFF(CURDATE(), DATE(first_visit)) as days_since_first,
                    COUNT(*) as user_count
                FROM users 
                GROUP BY DATEDIFF(CURDATE(), DATE(first_visit))
                ORDER BY days_since_first DESC
                LIMIT 10
            """)
            retention = cursor.fetchall()
            
            for r in retention:
                days = r['days_since_first']
                count = r['user_count']
                if days == 0:
                    print(f"   今天注册: {count} 用户")
                else:
                    print(f"   {days}天前注册: {count} 用户")
            
            # 抽牌习惯分析
            print(f"\n🎴 抽牌习惯分析:")
            cursor.execute("""
                SELECT 
                    DAYOFWEEK(date) as day_of_week,
                    CASE DAYOFWEEK(date)
                        WHEN 1 THEN '周日'
                        WHEN 2 THEN '周一'
                        WHEN 3 THEN '周二'
                        WHEN 4 THEN '周三'
                        WHEN 5 THEN '周四'
                        WHEN 6 THEN '周五'
                        WHEN 7 THEN '周六'
                    END as day_name,
                    COUNT(*) as reading_count
                FROM readings 
                WHERE date >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)
                GROUP BY DAYOFWEEK(date)
                ORDER BY day_of_week
            """)
            weekly_pattern = cursor.fetchall()
            
            if weekly_pattern:
                print("   过去30天每日抽牌分布:")
                for day in weekly_pattern:
                    print(f"   {day['day_name']}: {day['reading_count']} 次")
            
            # 正逆位分布
            cursor.execute("""
                SELECT direction, COUNT(*) as count
                FROM readings 
                GROUP BY direction
            """)
            direction_stats = cursor.fetchall()
            
            if direction_stats:
                print(f"\n   正逆位分布:")
                for stat in direction_stats:
                    print(f"   {stat['direction']}: {stat['count']} 次")
                    
    except Exception as e:
        print(f"❌ 分析过程出错: {e}")
    finally:
        conn.close()

def export_user_summary():
    """导出用户摘要报告"""
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"user_report_{timestamp}.txt"
            
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(f"塔罗牌应用用户报告\n")
                f.write(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write("=" * 50 + "\n\n")
                
                # 基础统计
                cursor.execute("SELECT COUNT(*) as total FROM users")
                total_users = cursor.fetchone()['total']
                
                cursor.execute("SELECT COUNT(*) as total FROM readings")
                total_readings = cursor.fetchone()['total']
                
                f.write(f"基础数据:\n")
                f.write(f"- 总用户数: {total_users}\n")
                f.write(f"- 总抽牌记录: {total_readings}\n")
                f.write(f"- 平均每用户抽牌: {total_readings/total_users:.2f} 次\n\n")
                
                # 详细用户列表
                cursor.execute("""
                    SELECT u.id, u.device_id, u.first_visit, u.last_visit, u.visit_count,
                           COUNT(r.id) as reading_count
                    FROM users u
                    LEFT JOIN readings r ON u.id = r.user_id
                    GROUP BY u.id
                    ORDER BY u.last_visit DESC
                """)
                users = cursor.fetchall()
                
                f.write("用户详情:\n")
                for user in users:
                    f.write(f"ID: {user['id']}\n")
                    f.write(f"  设备: {user['device_id']}\n")
                    f.write(f"  首次访问: {user['first_visit']}\n")
                    f.write(f"  最后访问: {user['last_visit']}\n")
                    f.write(f"  访问次数: {user['visit_count']}\n")
                    f.write(f"  抽牌记录: {user['reading_count']}\n\n")
            
            print(f"\n📄 用户报告已导出到: {filename}")
            
    except Exception as e:
        print(f"❌ 导出报告失败: {e}")
    finally:
        conn.close()

def interactive_monitor():
    """交互式监控"""
    while True:
        print("\n" + "="*60)
        print("🔮 塔罗牌用户系统监控工具")
        print("="*60)
        print("1. 实时监控")
        print("2. 详细分析")
        print("3. 导出报告")
        print("4. 连续监控 (每30秒)")
        print("0. 退出")
        
        choice = input("\n请选择功能 (0-4): ").strip()
        
        if choice == '1':
            monitor_users()
        elif choice == '2':
            detailed_user_analysis()
        elif choice == '3':
            export_user_summary()
        elif choice == '4':
            print("开始连续监控，按 Ctrl+C 停止...")
            try:
                while True:
                    monitor_users()
                    print(f"\n⏰ 等待30秒后刷新...")
                    time.sleep(30)
                    # 清屏（可选）
                    import os
                    os.system('clear' if os.name == 'posix' else 'cls')
            except KeyboardInterrupt:
                print("\n监控已停止")
        elif choice == '0':
            print("再见！")
            break
        else:
            print("无效选择，请重新输入")

if __name__ == "__main__":
    try:
        interactive_monitor()
    except KeyboardInterrupt:
        print("\n\n程序被中断")
    except Exception as e:
        print(f"\n程序出现错误: {e}")