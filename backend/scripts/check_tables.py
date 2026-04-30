import sqlite3
conn=sqlite3.connect('propscore.db')
cur=conn.cursor()
cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
print(cur.fetchall())
conn.close()
