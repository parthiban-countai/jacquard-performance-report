import asyncio, asyncpg, traceback
from datetime import datetime, timedelta
from src.aws_secrets import get_db_secrets


class Execute:
    def __init__(self):
        self.db_pool = None

    async def connect(self):
        if self.db_pool is None:
            try:
                async def init_connection(conn):
                    await conn.execute("SET timezone TO 'Asia/Kolkata'")

                self.db_pool = await asyncpg.create_pool(
                    database=get_db_secrets("DB_NAME"),
                    user=get_db_secrets("DB_USER"),
                    password=get_db_secrets("DB_PASSWORD"),
                    host=get_db_secrets("DB_HOST"),
                    port="5432",
                    min_size=1,
                    max_size=5,
                    init=init_connection,
                    timeout=10.0,
                    max_inactive_connection_lifetime=300,  # 5 min
                )
                print(f"✅ Connected to db")
                return True
            except Exception as e:
                print(f"❌ Connection failed to db: {e}")
                traceback.print_exc()
                return False

    async def close(self):
        if self.db_pool:
            await self.db_pool.close()
            self.db_pool = None

    async def select(self, query, *args):
        if self.db_pool is None:
            await self.connect()
        async with self.db_pool.acquire() as conn:
            try:
                rows = await conn.fetch(query, *args)
                main_data =  [dict(row) for row in rows]
                return main_data
            except Exception as e:
                traceback.print_exc()
                return []


class ClientSideDb:
    def __init__(self, db: Execute):
        self.execute = db

    async def connect_all_db(self):
        try:
            await self.execute.connect()
        except Exception:
            traceback.print_exc()
            return []

    async def mill_machine_name(self):
        try:
            query = """SELECT * FROM central_database.mill_details INNER JOIN central_database.machine_details ON mill_details.milldetails_id = machine_details.milldetails_id WHERE mill_details.milldetails_id = 2 ORDER BY machine_details.machinedetail_id ASC"""
            return await self.execute.select(query)
        except Exception:
            traceback.print_exc()
            return []

    async def uptime_data(self, start_date, end_date, db_name):
        try:
            query = f"""
                SELECT *, TO_CHAR(timestamp, 'YYYY-MM-DD HH24:MI:SS') AS formatted_timestamp FROM "{db_name}".uptime_status
                WHERE TO_CHAR(timestamp, 'YYYY-MM-DD HH24:MI') >= '{start_date}' AND TO_CHAR(timestamp, 'YYYY-MM-DD HH24:MI') < '{end_date}'
                ORDER BY uptimestatus_id ASC;
            """
            return await self.execute.select(query)
        except Exception:
            traceback.print_exc()
            return []

    async def active_cameras(self, db_name):
        try:
            query = f"""SELECT cam_name FROM "{db_name}".cam_details WHERE camsts_id = '1' ORDER BY cam_id ASC;"""
            return await self.execute.select(query)
        except Exception:
            traceback.print_exc()
            return []

    async def revolution_data(self, start_date, end_date, db_name):
        try:
            query = f"""
                SELECT rotation_id FROM "{db_name}".rotation_details
                WHERE TO_CHAR(timestamp, 'YYYY-MM-DD HH24:MI') >= '{start_date}' AND TO_CHAR(timestamp, 'YYYY-MM-DD HH24:MI') < '{end_date}'
                ORDER BY rotation_id ASC;
            """
            return await self.execute.select(query)
        except Exception:
            traceback.print_exc()
            return []

    async def alarm_data(self, start_date, end_date, db_name):
        try:
            query = f"""
                SELECT defect_type.defect_name FROM "{db_name}".alarm_status
                INNER JOIN "{db_name}".defect_details ON alarm_status.defect_id = defect_details.defect_id
                INNER JOIN "{db_name}".defect_type ON defect_details.defecttyp_id = defect_type.defecttyp_id
                WHERE TO_CHAR(alarm_status.timestamp, 'YYYY-MM-DD HH24:MI') >= '{start_date}' AND TO_CHAR(alarm_status.timestamp, 'YYYY-MM-DD HH24:MI') < '{end_date}'
                ORDER BY alarm_id ASC;
            """
            return await self.execute.select(query)
        except Exception:
            traceback.print_exc()
            return []

    async def last_updated_at(self, db_name):
        try:
            query = f"""SELECT TO_CHAR(timestamp, 'YYYY-MM-DD HH24:MI:SS') AS timestamp FROM "{db_name}".uptime_status ORDER BY uptimestatus_id DESC LIMIT 1;"""
            return await self.execute.select(query)
        except Exception:
            traceback.print_exc()
            return "-"