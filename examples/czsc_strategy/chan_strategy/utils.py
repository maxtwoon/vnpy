"""缠论策略工具函数"""
from datetime import datetime
from typing import List, Dict, Any


def parse_signal(signal_str: str) -> Dict[str, str]:
    """解析信号字符串"""
    parts = signal_str.split("_")
    if len(parts) != 7:
        raise ValueError(f"信号格式错误: {signal_str}, 应为 k1_k2_k3_v1_v2_v3_score")
    return {
        "k1": parts[0],
        "k2": parts[1],
        "k3": parts[2],
        "v1": parts[3],
        "v2": parts[4],
        "v3": parts[5],
        "score": int(parts[6])
    }


def signal_key(signal_str: str) -> str:
    """提取信号的key部分 (k1_k2_k3)"""
    parts = signal_str.split("_")
    return f"{parts[0]}_{parts[1]}_{parts[2]}"


def signal_value(signal_str: str) -> str:
    """提取信号的value部分 (v1_v2_v3_score)"""
    parts = signal_str.split("_")
    return f"{parts[3]}_{parts[4]}_{parts[5]}_{parts[6]}"
