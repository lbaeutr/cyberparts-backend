from enum import Enum


class RoleName(str, Enum):
    ADMIN = "ADMIN"
    GESTOR = "GESTOR"
    CLIENTE = "CLIENTE"


class OrderStatus(str, Enum):
    PENDING = "PENDING"
    PAID = "PAID"
    SHIPPED = "SHIPPED"
    DELIVERED = "DELIVERED"
    CANCELLED = "CANCELLED"
