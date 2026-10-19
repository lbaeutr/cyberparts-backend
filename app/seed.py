from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.enums import RoleName
from app.models.product import Product
from app.models.role import Role
from app.models.user import User

ROLES = [
    (RoleName.ADMIN, "Control total del sistema y gestion de usuarios."),
    (RoleName.GESTOR, "Gestiona el catalogo de productos y los pedidos."),
    (RoleName.CLIENTE, "Explora el catalogo y realiza pedidos."),
]

MATRIX_PASSWORD = "Matrix123!"

# (username, email, rol) — contrasena comun: MATRIX_PASSWORD
MATRIX_USERS = [
    ("neo", "neo@matrix.dev", RoleName.CLIENTE),
    ("trinity", "trinity@matrix.dev", RoleName.CLIENTE),
    ("morpheus", "morpheus@matrix.dev", RoleName.GESTOR),
    ("cypher", "cypher@matrix.dev", RoleName.CLIENTE),
    ("tank", "tank@matrix.dev", RoleName.GESTOR),
    ("dozer", "dozer@matrix.dev", RoleName.CLIENTE),
    ("switch", "switch@matrix.dev", RoleName.CLIENTE),
    ("apoc", "apoc@matrix.dev", RoleName.CLIENTE),
    ("mouse", "mouse@matrix.dev", RoleName.CLIENTE),
    ("niobe", "niobe@matrix.dev", RoleName.CLIENTE),
    ("link", "link@matrix.dev", RoleName.GESTOR),
    ("seraph", "seraph@matrix.dev", RoleName.CLIENTE),
    ("merovingian", "merovingian@matrix.dev", RoleName.GESTOR),
    ("oracle", "oracle@matrix.dev", RoleName.ADMIN),
    ("smith", "smith@matrix.dev", RoleName.ADMIN),
]

PRODUCTS = [
    # --- Procesadores ---
    {
        "name": "Neuro-Core X9",
        "description": "Procesador neuronal de 9 nucleos con overclock termico. Ideal para androides de combate.",
        "category": "Procesadores",
        "price": Decimal("1299.99"),
        "stock": 12,
    },
    {
        "name": "Micro-Computadora NEO-CHIP",
        "description": "Unidad de computo compacta compatible con la mayoria de chasis.",
        "category": "Procesadores",
        "price": Decimal("720.00"),
        "stock": 22,
    },
    {
        "name": "Quantum-Core Z1",
        "description": "Procesador cuantico experimental de 128 qubits para calculo predictivo.",
        "category": "Procesadores",
        "price": Decimal("3899.00"),
        "stock": 3,
    },
    {
        "name": "Cortex-Matrix V3",
        "description": "Unidad de IA con red neuronal de 64 canales y aprendizaje en tiempo real.",
        "category": "Procesadores",
        "price": Decimal("1540.00"),
        "stock": 14,
    },
    {
        "name": "Overclock Node R7",
        "description": "Modulo de overclocking con disipacion pasiva y monitorizacion de nucleos.",
        "category": "Procesadores",
        "price": Decimal("430.00"),
        "stock": 35,
    },
    # --- Servomotores ---
    {
        "name": "Servo Hidraulico KRAKEN",
        "description": "Servomotor de alto torque con refrigeracion liquida integrada.",
        "category": "Servomotores",
        "price": Decimal("349.50"),
        "stock": 40,
    },
    {
        "name": "Servo Neumatico VIPER",
        "description": "Servomotor neumatico de respuesta rapida para extremidades agiles.",
        "category": "Servomotores",
        "price": Decimal("275.40"),
        "stock": 48,
    },
    {
        "name": "Motor Angular TITAN",
        "description": "Motor de angulo limitado con par de 220Nm para articulaciones pesadas.",
        "category": "Servomotores",
        "price": Decimal("690.00"),
        "stock": 18,
    },
    {
        "name": "Servo Cuantico SPIN-X",
        "description": "Micro-servo de precision sub-milimetrica para cirugia robotica.",
        "category": "Servomotores",
        "price": Decimal("510.25"),
        "stock": 27,
    },
    # --- Sensores ---
    {
        "name": "Sensor Optico CHROME-EYE",
        "description": "Sensor visual 8K con vision nocturna y espectro infrarrojo.",
        "category": "Sensores",
        "price": Decimal("189.90"),
        "stock": 65,
    },
    {
        "name": "Radar Omnidireccional ECHO",
        "description": "Radar de barrido 360 grados con deteccion lidar integrada.",
        "category": "Sensores",
        "price": Decimal("620.00"),
        "stock": 20,
    },
    {
        "name": "Sensor Termico PYRO-X",
        "description": "Sensor termografico de alta resolucion con mapeo de calor en vivo.",
        "category": "Sensores",
        "price": Decimal("340.80"),
        "stock": 33,
    },
    {
        "name": "Biosensor VITALS",
        "description": "Monitor de signos vitales para androides medicos.",
        "category": "Sensores",
        "price": Decimal("415.00"),
        "stock": 24,
    },
    {
        "name": "Sensor de Proximidad GHOST",
        "description": "Detector de proximidad indetectable por espectro visible.",
        "category": "Sensores",
        "price": Decimal("155.00"),
        "stock": 70,
    },
    {
        "name": "Ojo Bionico IRIS-PRO",
        "description": "Reemplazo ocular con zoom optico 20x y vision espectral.",
        "category": "Sensores",
        "price": Decimal("990.00"),
        "stock": 13,
    },
    # --- Energia ---
    {
        "name": "Bateria de Fusion CELL-PULSE",
        "description": "Celda energetica de estado solido con 72h de autonomia continua.",
        "category": "Energia",
        "price": Decimal("599.00"),
        "stock": 25,
    },
    {
        "name": "Radiador Plasma COOLER-Z",
        "description": "Sistema de disipacion por plasma para cargas extremas.",
        "category": "Energia",
        "price": Decimal("455.20"),
        "stock": 30,
    },
    {
        "name": "Reactor Micro FUSION-M",
        "description": "Reactor de fusion compacto para operacion autonoma prolongada.",
        "category": "Energia",
        "price": Decimal("5200.00"),
        "stock": 2,
    },
    {
        "name": "Celda Solar NEOVOLT",
        "description": "Panel fotovoltaico flexible de alta eficiencia para chasis moviles.",
        "category": "Energia",
        "price": Decimal("280.00"),
        "stock": 44,
    },
    {
        "name": "Capacitor de Arranque JUMP-X",
        "description": "Condensador de descarga rapida para picos de energia instantaneos.",
        "category": "Energia",
        "price": Decimal("190.00"),
        "stock": 55,
    },
    # --- Chasis ---
    {
        "name": "Chasis Titano Aero-7",
        "description": "Estructura de titanio aeronautico con absorcion de impactos.",
        "category": "Chasis",
        "price": Decimal("879.00"),
        "stock": 8,
    },
    {
        "name": "Placas de Blindaje CARBON-9",
        "description": "Set de blindaje de fibra de carbono con nanorreparacion.",
        "category": "Chasis",
        "price": Decimal("640.00"),
        "stock": 16,
    },
    {
        "name": "Chasis Liviano SPECTRE",
        "description": "Estructura ultraligera para unidades de infiltracion y sigilo.",
        "category": "Chasis",
        "price": Decimal("1020.00"),
        "stock": 9,
    },
    {
        "name": "Exoesqueleto Frame HERCULES",
        "description": "Armazon de exoesqueleto resistente a impactos balisticos.",
        "category": "Chasis",
        "price": Decimal("2300.00"),
        "stock": 4,
    },
    # --- Modulos ---
    {
        "name": "Modulo Neural SYNAPSE",
        "description": "Interfaz cerebro-maquina con latencia inferior a 1ms.",
        "category": "Modulos",
        "price": Decimal("2450.00"),
        "stock": 5,
    },
    {
        "name": "Modulo IA CORTEX",
        "description": "Copiloto de inteligencia artificial con decision autonoma en combate.",
        "category": "Modulos",
        "price": Decimal("1850.00"),
        "stock": 7,
    },
    {
        "name": "Modulo de Carga DOCK-USB-X",
        "description": "Bahia de carga multi-puerto con gestion inteligente de baterias.",
        "category": "Modulos",
        "price": Decimal("130.00"),
        "stock": 80,
    },
    {
        "name": "Interfaz Holografica HOLO-GRID",
        "description": "Proyector holografico de campo volumetrico para HUD tactico.",
        "category": "Modulos",
        "price": Decimal("960.00"),
        "stock": 11,
    },
    {
        "name": "Nucleo de Memoria DATA-VAULT",
        "description": "Almacenamiento cuantico de 4TB con encriptacion biometrica.",
        "category": "Modulos",
        "price": Decimal("540.00"),
        "stock": 26,
    },
    # --- Actuadores ---
    {
        "name": "Actuador Magnetico GRIP-X",
        "description": "Pinza magnetica de precision para manipulacion industrial.",
        "category": "Actuadores",
        "price": Decimal("210.75"),
        "stock": 50,
    },
    {
        "name": "Brazo Robotico HYDRA-ARM",
        "description": "Brazo articulado de 7 grados de libertad con feedback haptico.",
        "category": "Actuadores",
        "price": Decimal("1650.00"),
        "stock": 6,
    },
    {
        "name": "Pierna Bionica STRIDER",
        "description": "Extremidad inferior bionica con amortiguacion adaptativa.",
        "category": "Actuadores",
        "price": Decimal("1450.00"),
        "stock": 8,
    },
    {
        "name": "Actuador Lineal PISTON-Z",
        "description": "Piston hidraulico lineal de carrera larga y alta precision.",
        "category": "Actuadores",
        "price": Decimal("320.00"),
        "stock": 38,
    },
    {
        "name": "Mano Haptica DEXTER-5",
        "description": "Mano robotica de 5 dedos con sensibilidad tactil completa.",
        "category": "Actuadores",
        "price": Decimal("780.00"),
        "stock": 20,
    },
    {
        "name": "Estabilizador Giro GYRO-CORE",
        "description": "Giroscopio estabilizador para equilibrio dinamico de unidades bipedas.",
        "category": "Actuadores",
        "price": Decimal("410.00"),
        "stock": 31,
    },
]


def seed(db: Session) -> None:
    for name, description in ROLES:
        role = db.scalar(select(Role).where(Role.name == name))
        if role is None:
            db.add(Role(name=name, description=description))
    db.commit()

    admin_role = db.scalar(select(Role).where(Role.name == RoleName.ADMIN))
    admin = db.scalar(select(User).where(User.username == settings.ADMIN_USERNAME))
    if admin is None:
        db.add(
            User(
                username=settings.ADMIN_USERNAME,
                email=settings.ADMIN_EMAIL,
                password_hash=hash_password(settings.ADMIN_PASSWORD),
                role_id=admin_role.id,
            )
        )
        db.commit()

    role_by_name = {r.name: r for r in db.scalars(select(Role)).all()}
    existing_usernames = set(db.scalars(select(User.username)).all())
    for username, email, role_name in MATRIX_USERS:
        if username in existing_usernames:
            continue
        db.add(
            User(
                username=username,
                email=email,
                password_hash=hash_password(MATRIX_PASSWORD),
                role_id=role_by_name[role_name].id,
            )
        )
    db.commit()

    existing_names = set(db.scalars(select(Product.name)).all())
    new_products = [Product(**data) for data in PRODUCTS if data["name"] not in existing_names]
    if new_products:
        db.add_all(new_products)
        db.commit()


def main() -> None:
    db = SessionLocal()
    try:
        seed(db)
        print("Seed completado: roles, admin y productos listos.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
