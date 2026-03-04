import asyncio, asyncpg, traceback
from datetime import datetime, timedelta


class Execute:
    def __init__(self, database="central_database", host="100.110.255.110"):
        self.database = database
        self.host = host
        self.db_pool = None

    async def connect(self, retries=1, delay=1):
        if self.db_pool is None:
            try:
                async def init_connection(conn):
                    await conn.execute("SET timezone TO 'Asia/Kolkata'")

                self.db_pool = await asyncpg.create_pool(
                    database=self.database,
                    user="postgres",
                    password="55555",
                    host=self.host,
                    port="5432",
                    ssl="disable",
                    min_size=1,
                    max_size=5,
                    init=init_connection,
                    timeout=10.0,
                    max_inactive_connection_lifetime=300,  # 5 min
                )
                print(f"✅ Connected to {self.database}")
                return True
            except Exception as e:
                print(f"❌ Connection failed {self.database} in {self.host}")
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
        self.dbconnection = {}

    async def connect_all_db(self):
        try:
            all_db_names = await self.mill_machine_name()

            for item in all_db_names:
                db_name = item["db_name"]
                droplet_ip = item["droplet_ip"]
                self.dbconnection[db_name] = Execute(db_name, droplet_ip)
                await self.dbconnection[db_name].connect()
        except Exception:
            traceback.print_exc()
            return []

    async def mill_machine_name(self):
        try:
            query = """SELECT * FROM public.mill_details INNER JOIN public.machine_details ON mill_details.milldetails_id = machine_details.milldetails_id WHERE mill_details.milldetails_id = 2 ORDER BY machine_details.machinedetail_id ASC"""
            return await self.execute.select(query)
        except Exception:
            traceback.print_exc()
            return []

    async def uptime_data(self, start_date, end_date):
        try:
            query = f"""
                SELECT *, TO_CHAR(timestamp, 'YYYY-MM-DD HH24:MI:SS') AS formatted_timestamp FROM public.uptime_status
                WHERE TO_CHAR(timestamp, 'YYYY-MM-DD HH24:MI') >= '{start_date}' AND TO_CHAR(timestamp, 'YYYY-MM-DD HH24:MI') < '{end_date}'
                ORDER BY uptimestatus_id ASC;
            """
            return await self.dbconnection["jacquard-1"].select(query)
        except Exception:
            traceback.print_exc()
            return []

    async def active_cameras(self):
        try:
            query = """SELECT cam_name FROM public.cam_details WHERE camsts_id = '1' ORDER BY cam_id ASC;"""
            return await self.dbconnection["jacquard-1"].select(query)
        except Exception:
            traceback.print_exc()
            return []

    async def revolution_data(self, start_date, end_date):
        try:
            query = f"""
                SELECT rotation_id FROM public.rotation_details
                WHERE TO_CHAR(timestamp, 'YYYY-MM-DD HH24:MI') >= '{start_date}' AND TO_CHAR(timestamp, 'YYYY-MM-DD HH24:MI') < '{end_date}'
                ORDER BY rotation_id ASC;
            """
            return await self.dbconnection["jacquard-1"].select(query)
        except Exception:
            traceback.print_exc()
            return []

    async def alarm_data(self, start_date, end_date):
        try:
            query = f"""
                SELECT defect_type.defect_name FROM public.alarm_status
                INNER JOIN public.defect_details ON alarm_status.defect_id = defect_details.defect_id
                INNER JOIN public.defect_type ON defect_details.defecttyp_id = defect_type.defecttyp_id
                WHERE TO_CHAR(alarm_status.timestamp, 'YYYY-MM-DD HH24:MI') >= '{start_date}' AND TO_CHAR(alarm_status.timestamp, 'YYYY-MM-DD HH24:MI') < '{end_date}'
                ORDER BY alarm_id ASC;
            """
            return await self.dbconnection["jacquard-1"].select(query)
        except Exception:
            traceback.print_exc()
            return []