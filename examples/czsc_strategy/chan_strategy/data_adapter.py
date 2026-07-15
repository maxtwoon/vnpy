"""
SQLite数据适配器 - 从本地数据库加载K线数据并转换为czsc RawBar格式

数据库路径: D:\\BaiduNetdiskDownload\\新数据库\\ssquant数据库_20260425\\kline_data.db
"""
import sqlite3
import pandas as pd
from datetime import datetime, date
from typing import List, Optional
from pathlib import Path

# czsc库导入
from czsc.objects import RawBar, Freq


def _trading_day_for_bar(
    bar,
    trading_dates: set[date],
    night_session_start_hour: int,
    notes: list[str],
) -> date:
    """Map a single bar to its exchange trading day (A39 design 4.1)."""
    bar_date = bar.dt.date()
    bar_hour = bar.dt.hour

    if bar_hour >= night_session_start_hour:
        # Evening session belongs to the next trading date strictly after bar_date.
        later = [d for d in trading_dates if d > bar_date]
        if later:
            return min(later)
        # Tail-of-data fallback: keep bar_date and record a note.
        notes.append(f"evening bar {bar.dt} has no later trading date; fallback to {bar_date}")
        return bar_date

    # Non-evening bar: its own date if it is a trading date, else roll forward.
    if bar_date in trading_dates:
        return bar_date
    later_or_same = [d for d in trading_dates if d >= bar_date]
    if later_or_same:
        return min(later_or_same)
    # Defensive fallback (should not happen when trading_dates is non-empty).
    notes.append(f"non-evening bar {bar.dt} has no trading date; fallback to {bar_date}")
    return bar_date


def _resample_daily_trading_calendar(
    bars: List[RawBar],
    target_freq: Freq,
    night_session_start_hour: int,
) -> List[RawBar]:
    """Daily aggregation by exchange trading day (A39 Phase 1)."""
    symbol = bars[0].symbol
    day_session_hours = range(8, 16)
    trading_dates = sorted({
        bar.dt.date() for bar in bars if bar.dt.hour in day_session_hours
    })

    if not trading_dates:
        # No day-session bars: fall back to natural date to avoid producing nothing.
        return _resample_daily_natural(bars, target_freq)

    trading_date_set = set(trading_dates)
    notes: list[str] = []

    resampled: List[RawBar] = []
    group: List[RawBar] = []
    current_trading_day: Optional[date] = None

    for bar in bars:
        trading_day = _trading_day_for_bar(
            bar, trading_date_set, night_session_start_hour, notes
        )
        if current_trading_day is None:
            current_trading_day = trading_day
            group = [bar]
        elif trading_day == current_trading_day:
            group.append(bar)
        else:
            if group:
                resampled.append(_merge_bars(group, symbol, target_freq, len(resampled)))
            group = [bar]
            current_trading_day = trading_day

    if group:
        resampled.append(_merge_bars(group, symbol, target_freq, len(resampled)))

    return resampled


def _resample_daily_natural(bars: List[RawBar], target_freq: Freq) -> List[RawBar]:
    """Daily aggregation by natural calendar date (legacy byte-identical path)."""
    symbol = bars[0].symbol
    resampled: List[RawBar] = []
    group: List[RawBar] = []
    current_date: Optional[date] = None

    for bar in bars:
        bar_date = bar.dt.date()
        if current_date is None:
            current_date = bar_date
            group = [bar]
        elif bar_date == current_date:
            group.append(bar)
        else:
            if group:
                resampled.append(_merge_bars(group, symbol, target_freq, len(resampled)))
            group = [bar]
            current_date = bar_date

    if group:
        resampled.append(_merge_bars(group, symbol, target_freq, len(resampled)))

    return resampled


def resample_bars(
    bars: List[RawBar],
    target_freq: Freq,
    target_minutes: int = None,
    daily_agg: str = None,
    night_session_start_hour: int = None,
) -> List[RawBar]:
    """
    将低频K线合成为高频K线（如1分钟→30分钟，1分钟→日线）

    :param bars: 原始K线列表（需按时间排序）
    :param target_freq: 目标频率的czsc Freq对象
    :param target_minutes: 目标周期分钟数。日线传None，会按自然日聚合
    :param daily_agg: 日线聚合模式 ("natural" | "trading_calendar")；None 则从 STRATEGY_CONFIG 读取
    :param night_session_start_hour: 夜盘开始小时；None 则从 STRATEGY_CONFIG 读取
    :return: 合成后的RawBar列表

    支持:
    - 1分钟 → 5/15/30/60/120分钟 (按固定间隔聚合)
    - 1分钟 → 日线 (按自然日聚合或按交易日聚合)
    """
    if not bars:
        return []

    if target_minutes and target_minutes > 0:
        # 分钟级别聚合: 按固定间隔切分
        symbol = bars[0].symbol
        resampled = []
        group = []
        group_start_minute = None

        for bar in bars:
            # 计算当前bar在当天的分钟偏移
            bar_minute = bar.dt.hour * 60 + bar.dt.minute
            # 计算所属的组号
            group_idx = bar_minute // target_minutes

            if group_start_minute is None:
                group_start_minute = group_idx
                group = [bar]
            elif group_idx == group_start_minute and bar.dt.date() == group[-1].dt.date():
                group.append(bar)
            else:
                # 新的一组，先保存上一组
                if group:  # pragma: no branch - group is always populated before rollover
                    resampled.append(_merge_bars(group, symbol, target_freq, len(resampled)))
                group = [bar]
                group_start_minute = group_idx

        # 保存最后一组
        if group:  # pragma: no branch - final group exists after at least one bar
            resampled.append(_merge_bars(group, symbol, target_freq, len(resampled)))
        return resampled

    # 日线聚合
    if daily_agg is None or night_session_start_hour is None:
        # Lazy import to keep the module usable in contexts without config.
        from chan_strategy.config import STRATEGY_CONFIG
        if daily_agg is None:
            daily_agg = STRATEGY_CONFIG.get("daily_agg", "natural")
        if night_session_start_hour is None:
            night_session_start_hour = STRATEGY_CONFIG.get("night_session_start_hour", 20)

    if daily_agg == "trading_calendar":
        return _resample_daily_trading_calendar(bars, target_freq, night_session_start_hour)

    return _resample_daily_natural(bars, target_freq)


def _merge_bars(group: List[RawBar], symbol: str, freq: Freq, bar_id: int) -> RawBar:
    """将一组K线合并为一根"""
    return RawBar(
        symbol=symbol,
        id=bar_id,
        dt=group[-1].dt,  # 使用最后一根K线的时间作为该周期的时间戳
        freq=freq,
        open=group[0].open,
        close=group[-1].close,
        high=max(b.high for b in group),
        low=min(b.low for b in group),
        vol=sum(b.vol for b in group),
        amount=sum(b.amount for b in group),
    )


class SqliteDataAdapter:
    """SQLite K线数据适配器"""

    def __init__(self, db_path: str):
        """
        初始化数据适配器

        :param db_path: SQLite数据库文件路径
        """
        self.db_path = db_path
        self._conn = None
        self._table_info = None

    @property
    def conn(self):
        """懒加载数据库连接"""
        if self._conn is None:
            if not Path(self.db_path).exists():
                raise FileNotFoundError(f"数据库文件不存在: {self.db_path}")
            self._conn = sqlite3.connect(self.db_path)
        return self._conn

    def close(self):
        """关闭数据库连接"""
        if self._conn:
            self._conn.close()
            self._conn = None

    def get_tables(self) -> List[str]:
        """获取所有表名"""
        cursor = self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
        return [row[0] for row in cursor.fetchall()]

    def get_table_schema(self, table_name: str) -> List[dict]:
        """获取表结构"""
        cursor = self.conn.execute(f"PRAGMA table_info({table_name})")
        columns = []
        for row in cursor.fetchall():
            columns.append({
                "cid": row[0],
                "name": row[1],
                "type": row[2],
                "notnull": row[3],
                "default": row[4],
                "pk": row[5]
            })
        return columns

    def get_symbols(self, table_name: str = None) -> List[str]:
        """获取所有可用的股票代码"""
        if table_name is None:
            tables = self.get_tables()
            table_name = tables[0] if tables else None
        if not table_name:
            return []

        # 尝试不同的可能列名
        for col in ["symbol", "code", "stock_code", "ts_code"]:
            try:
                cursor = self.conn.execute(
                    f"SELECT DISTINCT {col} FROM {table_name} LIMIT 100"
                )
                return [row[0] for row in cursor.fetchall()]
            except sqlite3.OperationalError:
                continue
        return []

    def get_sample_data(self, table_name: str = None, limit: int = 5) -> pd.DataFrame:
        """获取样本数据，用于分析表结构"""
        if table_name is None:
            tables = self.get_tables()
            table_name = tables[0] if tables else None
        if not table_name:
            return pd.DataFrame()
        return pd.read_sql(f"SELECT * FROM {table_name} LIMIT {limit}", self.conn)

    def load_kline_data(
        self,
        symbol: str,
        start_date: str = None,
        end_date: str = None,
        freq: str = None,
        table_name: str = None
    ) -> pd.DataFrame:
        """
        加载K线数据

        :param symbol: 股票代码
        :param start_date: 开始日期 (YYYY-MM-DD)
        :param end_date: 结束日期 (YYYY-MM-DD)
        :param freq: 频率过滤（如 'd', '5', '30' 等）
        :param table_name: 指定表名，默认使用第一个表
        :return: DataFrame
        """
        if table_name is None:
            tables = self.get_tables()
            table_name = tables[0] if tables else None
        if not table_name:
            raise ValueError("数据库中没有找到数据表")

        # 构建查询 - 需要根据实际表结构适配
        # 先获取表的列名
        schema = self.get_table_schema(table_name)
        col_names = [col["name"] for col in schema]

        # 识别关键列
        symbol_col = self._find_column(col_names, ["symbol", "code", "stock_code", "ts_code"])
        date_col = self._find_column(col_names, ["datetime", "date", "trade_date", "dt", "time"])
        freq_col = self._find_column(col_names, ["frequency", "freq", "period", "interval"])

        if not symbol_col or not date_col:
            raise ValueError(f"无法识别表 {table_name} 的关键列。列名: {col_names}")

        # 构建WHERE条件（品种代码大小写不敏感，兼容历史大写与近期小写记录）
        conditions = [f"{symbol_col} = ? COLLATE NOCASE"]
        params = [symbol]

        if start_date:
            conditions.append(f"{date_col} >= ?")
            params.append(start_date)
        if end_date:
            # 当 end_date 只给日期时，需要包含该日期的全部时间。
            # 例如 '2026-07-06' 应等价于 '2026-07-06 23:59:59'，否则时间戳会被排除。
            end_param = str(end_date)
            if len(end_param) <= 10 and " " not in end_param:
                end_param = f"{end_param} 23:59:59"
            conditions.append(f"{date_col} <= ?")
            params.append(end_param)
        if freq and freq_col:
            conditions.append(f"{freq_col} = ?")
            params.append(freq)

        where_clause = " AND ".join(conditions)
        query = f"SELECT * FROM {table_name} WHERE {where_clause} ORDER BY {date_col}"

        df = pd.read_sql(query, self.conn, params=params)
        return df

    def load_raw_bars(
        self,
        symbol: str,
        freq: str = "d",
        start_date: str = None,
        end_date: str = None,
        table_name: str = None,
        unparseable_count: list[int] | None = None,
    ) -> List[RawBar]:
        """
        加载并转换为czsc RawBar格式

        :param symbol: 股票代码
        :param freq: 频率 ('d'=日线, '5'=5分钟, '30'=30分钟等)
        :param start_date: 开始日期
        :param end_date: 结束日期
        :param table_name: 表名
        :param unparseable_count: 可选的可变容器（长度为1的列表），用于接收
            因 datetime 无法解析而被跳过的行数。
        :return: RawBar列表
        """
        df = self.load_kline_data(symbol, start_date, end_date, freq, table_name)

        # A52 adjustment-method declaration. Confirmed by
        # diagnostics/contract_adjustment_verification.py on 2026-07-13:
        # the 888 continuous-contract tables (AP888/RB888/SC888/A888/ZN888) are
        # raw, unadjusted contract splices. They carry a ``real_symbol`` column
        # but no adjustment/factor columns, and price discontinuities exist at
        # rollover transition dates. This matches the A34 H4 ``found_spliced``
        # finding, which this codebase therefore treats as still holding.
        # No front-adjustment, back-adjustment, or re-splicing is performed here.

        if df.empty:
            return []

        # 映射频率到czsc Freq
        freq_map = {
            "1": Freq.F1, "5": Freq.F5, "15": Freq.F15,
            "30": Freq.F30, "60": Freq.F60, "120": Freq.F120,
            "d": Freq.D, "w": Freq.W, "m": Freq.M,
            "1min": Freq.F1, "5min": Freq.F5, "15min": Freq.F15,
            "30min": Freq.F30, "60min": Freq.F60,
            "daily": Freq.D, "day": Freq.D,
        }
        czsc_freq = freq_map.get(str(freq).lower(), Freq.D)

        # 识别列名映射
        col_names = list(df.columns)
        open_col = self._find_column(col_names, ["open", "open_price", "开盘价"])
        high_col = self._find_column(col_names, ["high", "high_price", "最高价"])
        low_col = self._find_column(col_names, ["low", "low_price", "最低价"])
        close_col = self._find_column(col_names, ["close", "close_price", "收盘价"])
        vol_col = self._find_column(col_names, ["volume", "vol", "成交量"])
        amount_col = self._find_column(col_names, ["amount", "turnover", "成交额"])
        date_col = self._find_column(col_names, ["datetime", "date", "trade_date", "dt", "time"])

        bars = []
        unparseable_rows = 0
        for _i, row in df.iterrows():
            # 解析日期时间
            dt_val = row[date_col]
            if isinstance(dt_val, str):
                # 尝试多种日期格式
                for fmt in ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y%m%d", "%Y/%m/%d"]:
                    try:
                        dt = datetime.strptime(dt_val, fmt)
                        break
                    except ValueError:
                        continue
                else:
                    unparseable_rows += 1
                    continue  # 跳过无法解析的行
            elif isinstance(dt_val, (int, float)):
                dt = pd.Timestamp(dt_val).to_pydatetime()
            else:
                dt = pd.Timestamp(dt_val).to_pydatetime()

            bar = RawBar(
                symbol=symbol,
                id=len(bars),
                dt=dt,
                freq=czsc_freq,
                open=float(row[open_col]),
                close=float(row[close_col]),
                high=float(row[high_col]),
                low=float(row[low_col]),
                vol=float(row[vol_col]) if vol_col else 0,
                amount=float(row[amount_col]) if amount_col else 0,
            )
            bars.append(bar)

        if unparseable_count is not None:
            unparseable_count[0] = unparseable_rows

        return bars

    def _find_column(self, columns: List[str], candidates: List[str]) -> Optional[str]:
        """从列名列表中查找匹配的列"""
        columns_lower = {c.lower(): c for c in columns}
        for candidate in candidates:
            if candidate.lower() in columns_lower:
                return columns_lower[candidate.lower()]
        return None

    def inspect_database(self) -> dict:
        """检查数据库结构，返回完整信息"""
        info = {"tables": {}}
        for table in self.get_tables():
            schema = self.get_table_schema(table)
            sample = self.get_sample_data(table, limit=3)
            row_count = self.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            info["tables"][table] = {
                "schema": schema,
                "sample": sample.to_dict() if not sample.empty else {},
                "row_count": row_count
            }
        return info


def inspect_database():  # pragma: no cover - interactive inspection helper
    """快速检查数据库结构的辅助函数"""
    from .config import SQLITE_DB_PATH

    adapter = SqliteDataAdapter(SQLITE_DB_PATH)
    try:
        print(f"数据库路径: {SQLITE_DB_PATH}")
        print(f"文件存在: {Path(SQLITE_DB_PATH).exists()}")
        print()

        tables = adapter.get_tables()
        print(f"数据表 ({len(tables)}个): {tables}")
        print()

        for table in tables[:3]:  # 最多显示3个表
            print(f"--- 表: {table} ---")
            schema = adapter.get_table_schema(table)
            print("列结构:")
            for col in schema:
                print(f"  {col['name']} ({col['type']})")

            sample = adapter.get_sample_data(table, limit=3)
            if not sample.empty:
                print("样本数据:")
                print(sample.to_string(index=False))
            print()

        adapter.close()
    except Exception as e:
        print(f"错误: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    inspect_database()
