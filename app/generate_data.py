import pyodbc
import time
import random
import os
from datetime import datetime, timedelta

# Konfiguration
SERVER = os.getenv('DB_SERVER', '127.0.0.1')
USER = os.getenv('DB_USER', 'sa')
PASSWORD = os.getenv('DB_PASSWORD', 'CandyFactory2025!')
DB_NAME = os.getenv('DB_NAME', 'CandyDB')

def get_conn(autocommit=True):
    drivers = [d for d in pyodbc.drivers() if 'ODBC Driver 17' in d]
    driver = drivers[0] if drivers else 'ODBC Driver 17 for SQL Server'
    conn_str = f'DRIVER={{{driver}}};SERVER={SERVER};UID={USER};PWD={PASSWORD};TrustServerCertificate=yes'
    if not autocommit: conn_str += f';DATABASE={DB_NAME}'
    try: return pyodbc.connect(conn_str, autocommit=autocommit)
    except Exception as e:
        print(f"Väntar på databas... ({e})")
        return None

def init_db():
    print("--- 1. Initierar Fabriken 3.0 ---")
    time.sleep(10)
    
    conn = get_conn()
    if conn:
        conn.execute(f"IF NOT EXISTS (SELECT * FROM sys.databases WHERE name = '{DB_NAME}') CREATE DATABASE {DB_NAME}")
        conn.close()

    conn = get_conn(autocommit=False)
    if not conn: return
    cursor = conn.cursor()
    
    # --- SKAPA TABELLER ---
    tables = [
        "IF OBJECT_ID('Sensors', 'U') IS NULL CREATE TABLE Sensors (SensorID INT PRIMARY KEY IDENTITY, MachineID INT, SensorType NVARCHAR(50), Value FLOAT, AlarmID INT, Timestamp DATETIME)",
        "IF OBJECT_ID('Alarms', 'U') IS NULL CREATE TABLE Alarms (AlarmID INT PRIMARY KEY IDENTITY, MachineID INT, AlarmCode NVARCHAR(50), Description NVARCHAR(200), StartTime DATETIME, EndTime DATETIME, DurationMinutes INT)",
        "IF OBJECT_ID('Machines', 'U') IS NULL CREATE TABLE Machines (MachineID INT PRIMARY KEY IDENTITY, DeptID INT, Name NVARCHAR(50))",
        "IF OBJECT_ID('Departments', 'U') IS NULL CREATE TABLE Departments (DeptID INT PRIMARY KEY IDENTITY, Name NVARCHAR(50))",
        "IF OBJECT_ID('Products', 'U') IS NULL CREATE TABLE Products (ProductID INT PRIMARY KEY IDENTITY, Name NVARCHAR(50), DifficultyLevel INT, IdealSpeedKgH INT)",
        "IF OBJECT_ID('Orders', 'U') IS NULL CREATE TABLE Orders (OrderID INT PRIMARY KEY IDENTITY, Customer NVARCHAR(100), ProductID INT, AmountKg INT, DueDate DATETIME, Status NVARCHAR(20))",
        "IF OBJECT_ID('ProductionLog', 'U') IS NULL CREATE TABLE ProductionLog (LogID INT PRIMARY KEY IDENTITY, MachineID INT, ProductID INT, StartTime DATETIME, DurationHours INT, ProducedKg INT, ScrappedKg INT)"
    ]
    for t in tables: cursor.execute(t)
    conn.commit()
    
    # --- KOLLA DATA ---
    cursor.execute("SELECT COUNT(*) FROM ProductionLog")
    if cursor.fetchone()[0] < 50:
        print("--- 2. Genererar Master Data (Produkter & Avdelningar) ---")
        cursor.execute("DELETE FROM Sensors"); cursor.execute("DELETE FROM Alarms"); 
        cursor.execute("DELETE FROM ProductionLog"); cursor.execute("DELETE FROM Orders");
        cursor.execute("DELETE FROM Machines"); cursor.execute("DELETE FROM Departments"); cursor.execute("DELETE FROM Products");
        conn.commit()
        
        populate_master_data(cursor)
        populate_history(cursor, conn)
    else:
        print("Data finns redan.")
    conn.close()

def populate_master_data(cursor):
    # Avdelningar
    depts = ["Intag", "Blanderi", "Press", "Pack", "Utlastning"]
    for d in depts: cursor.execute("INSERT INTO Departments (Name) VALUES (?)", d)
    
    # Produkter (Namn, Svårighetsgrad 1-5, Ideal hastighet kg/h)
    products = [
        ("Hasses sega gubbar", 5, 800),   # Tuff mot maskinerna!
        ("Lisas Hallonbåtar", 3, 1000),   # Kladdig
        ("Dunder-Lakrits", 4, 900),       # Hård
        ("Sur-Sverre", 2, 1200),          # Dammar (Kvalitetsproblem)
        ("Choco-Crunch", 3, 950)          # Temperaturkänslig
    ]
    for p in products: cursor.execute("INSERT INTO Products (Name, DifficultyLevel, IdealSpeedKgH) VALUES (?, ?, ?)", p[0], p[1], p[2])
    
    # Maskiner
    cursor.execute("SELECT DeptID FROM Departments")
    dept_ids = [row[0] for row in cursor.fetchall()]
    for d_id in dept_ids:
        for i in range(1, 6):
            cursor.execute("INSERT INTO Machines (DeptID, Name) VALUES (?, ?)", d_id, f"Maskin_{d_id}_{i}")

def populate_history(cursor, conn):
    print("--- 3. Simulerar produktion 2024 -> Idag ---")
    
    # Hämta IDs
    cursor.execute("SELECT MachineID, DeptID FROM Machines")
    machines = cursor.fetchall() # [(id, dept), ...]
    cursor.execute("SELECT ProductID, Name, DifficultyLevel, IdealSpeedKgH FROM Products")
    products = cursor.fetchall()
    
    start_date = datetime(2024, 1, 1)
    end_date = datetime.now() + timedelta(days=30) # Vi genererar även framtida ordrar
    
    current_date = start_date
    customers = ["GodisGrossisten AB", "Söta Saker", "CinemaCandy", "Kiosk-Kungen", "Stormarknaden"]
    
    while current_date <= end_date:
        is_future = current_date > datetime.now()
        
        # 1. SKAPA ORDRAR
        if random.random() > 0.6: # 40% chans för ny order varje dag
            cust = random.choice(customers)
            prod = random.choice(products)
            amount = random.randint(1000, 20000)
            due = current_date + timedelta(days=random.randint(5, 14))
            status = "Pending" if is_future else "Done"
            
            cursor.execute("INSERT INTO Orders (Customer, ProductID, AmountKg, DueDate, Status) VALUES (?, ?, ?, ?, ?)",
                           cust, prod[0], amount, due, status)
        
        # 2. PRODUKTION & LARM (Bara om det är historia)
        if not is_future:
            for m in machines:
                m_id, dept_id = m
                if random.random() > 0.8: continue # Maskinen står still ibland
                
                # Välj en produkt att köra
                prod = random.choice(products) # (ID, Name, Diff, Speed)
                prod_id, prod_name, difficulty, speed = prod
                
                # Produktionsfakta
                run_hours = random.randint(4, 16)
                base_production = run_hours * speed
                
                # "Sur-Sverre" ger mer spill (Scrap)
                scrap_factor = 0.15 if "Sur-Sverre" in prod_name else 0.02
                scrapped = int(base_production * random.uniform(0.01, scrap_factor))
                produced = int(base_production - scrapped)
                
                cursor.execute("""
                    INSERT INTO ProductionLog (MachineID, ProductID, StartTime, DurationHours, ProducedKg, ScrappedKg)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, m_id, prod_id, current_date, run_hours, produced, scrapped)
                
                # LARM-LOGIK BASERAT PÅ PRODUKT
                # Hasses sega gubbar (Diff 5) skapar larm!
                alarm_chance = 0.1 + (difficulty * 0.05) # 0.1 till 0.35 risk
                
                if random.random() < alarm_chance:
                    # Skapa ett larm kopplat till denna körning
                    larm_time = current_date + timedelta(hours=random.randint(1, run_hours))
                    
                    # Kontextuella larm
                    if "Hasses" in prod_name:
                        code, desc = "A02", "Motoröverlast (Hårt material)"
                    elif "Sur-Sverre" in prod_name:
                        code, desc = "A10", "Fotocell blockerad (Damm)"
                    elif "Choco" in prod_name:
                        code, desc = "A04", "Temp hög (Smältvarning)"
                    else:
                        code, desc = "A99", "Allmänt maskinfel"
                        
                    duration = random.randint(10, 120)
                    cursor.execute("INSERT INTO Alarms (MachineID, AlarmCode, Description, StartTime, EndTime, DurationMinutes) VALUES (?, ?, ?, ?, ?, ?)",
                                   m_id, code, desc, larm_time, larm_time + timedelta(minutes=duration), duration)
                    alarm_id = cursor.execute("SELECT @@IDENTITY").fetchone()[0]
                    
                    # Sensorer
                    cursor.execute("INSERT INTO Sensors (MachineID, SensorType, Value, AlarmID, Timestamp) VALUES (?, ?, ?, ?, ?)",
                                   m_id, "Vibration", random.uniform(5, 15), alarm_id, larm_time)

        current_date += timedelta(days=1)
        if current_date.day == 1: conn.commit() # Spara månadsvis
        
    conn.commit()
    print("--- Generering Klar ---")

if __name__ == "__main__":
    init_db()
