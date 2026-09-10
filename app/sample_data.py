"""样例数据已移除。

历史：曾用于初始化 2 条示例竞赛（c_001/c_002），
现已被真实数据（imp_001~015）替代。
seed_if_empty 保留空实现以防调用方报错，但不再写入任何数据。
"""
from sqlalchemy.orm import Session

from .database import SessionLocal


def seed_if_empty() -> None:
    """空实现：不再写入样例数据。

    数据库初始化时仍会调用此函数（database.init_db），
    但函数体不做任何操作，确保部署时不会重新创建样例。
    """
    return
