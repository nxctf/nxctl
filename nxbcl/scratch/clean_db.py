import sqlite3
conn = sqlite3.connect("data_nxbcl/nxbcl.db")
conn.execute("UPDATE instances SET status = 'stopped'")
conn.commit()
print("Successfully marked all instances as stopped in data_nxbcl/nxbcl.db")
