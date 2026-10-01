import enum


class StrEnum(str, enum.Enum):
    pass


class UserStatus(StrEnum):
    ACTIVE = "active"
    BANNED = "banned"
    PENDING = "pending"


class UserRole(StrEnum):
    CUSTOMER = "customer"
    ADMIN = "admin"
    MODERATOR = "moderator"
    SELLER = "seller"

class ProductStatus(StrEnum):
    OUTOFSTOCK = "out_of_stock"
    AVAILABLE = "available" 
    DISCONTINUED = "discontinued"


class OrderStatus(StrEnum):
    PENDING = "pending"
    PAID = "paid"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELED = "canceled"


class PaymentStatus(StrEnum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    REFUNDED = "refunded"


class PaymentMethod(StrEnum):
    CARD = "card"
    BANKTRANSFER = "bank_transfer"
    CRYPTO = "crypto"
    CASH = "cash"

class RefundStatus(StrEnum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"

class DiscountType(StrEnum):
    PERCENTAGE = "percentage"
    FIXED = "fixed"
    FREE_SHIPPING = "free_shipping"
    