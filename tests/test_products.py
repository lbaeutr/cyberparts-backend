from decimal import Decimal

import pytest


def product_payload(**overrides):
    payload = {
        "name": "Sensor Termico",
        "description": "Sensor de temperatura de alta precision",
        "category": "Sensores",
        "price": "49.90",
        "stock": 5,
        "image_url": None,
        "is_active": True,
    }
    payload.update(overrides)
    return payload


def test_list_products_excludes_inactive_by_default(client, create_product):
    create_product(name="Activo")
    create_product(name="Inactivo", is_active=False)

    response = client.get("/api/products")

    assert response.status_code == 200
    names = [p["name"] for p in response.json()]
    assert names == ["Activo"]


def test_list_products_can_include_inactive(client, create_product):
    create_product(name="Activo")
    create_product(name="Inactivo", is_active=False)

    response = client.get("/api/products", params={"only_active": "false"})

    assert response.status_code == 200
    assert {p["name"] for p in response.json()} == {"Activo", "Inactivo"}


def test_list_products_filter_by_category(client, create_product):
    create_product(name="Servo", category="Servomotores")
    create_product(name="Sensor", category="Sensores")

    response = client.get("/api/products", params={"category": "Sensores"})

    assert response.status_code == 200
    assert [p["name"] for p in response.json()] == ["Sensor"]


def test_list_products_search_is_case_insensitive(client, create_product):
    create_product(name="Servomotor X1")
    create_product(name="Sensor Termico")

    response = client.get("/api/products", params={"search": "servo"})

    assert response.status_code == 200
    assert {p["name"] for p in response.json()} == {"Servomotor X1"}


def test_list_products_pagination(client, create_product):
    for index in range(5):
        create_product(name=f"Pieza {index}")

    first_page = client.get("/api/products", params={"limit": 2})
    second_page = client.get("/api/products", params={"limit": 2, "skip": 2})

    assert [p["name"] for p in first_page.json()] == ["Pieza 0", "Pieza 1"]
    assert [p["name"] for p in second_page.json()] == ["Pieza 2", "Pieza 3"]


def test_get_product(client, create_product):
    product = create_product(name="Servomotor X1")

    response = client.get(f"/api/products/{product.id}")

    assert response.status_code == 200
    assert response.json()["id"] == product.id


def test_get_missing_product_returns_404(client):
    response = client.get("/api/products/9999")

    assert response.status_code == 404


@pytest.mark.parametrize("fixture_name", ["admin_headers", "gestor_headers"])
def test_staff_can_create_product(client, request, fixture_name):
    headers = request.getfixturevalue(fixture_name)

    response = client.post("/api/products", json=product_payload(), headers=headers)

    assert response.status_code == 201, response.text
    data = response.json()
    assert data["name"] == "Sensor Termico"
    assert Decimal(data["price"]) == Decimal("49.90")


def test_cliente_cannot_create_product(client, cliente_headers):
    response = client.post("/api/products", json=product_payload(), headers=cliente_headers)

    assert response.status_code == 403


def test_anonymous_cannot_create_product(client):
    response = client.post("/api/products", json=product_payload())

    assert response.status_code == 401


@pytest.mark.parametrize(
    "overrides",
    [
        {"name": "x"},
        {"price": "0"},
        {"stock": -1},
        {"category": ""},
    ],
)
def test_create_product_validation_errors(client, admin_headers, overrides):
    response = client.post(
        "/api/products", json=product_payload(**overrides), headers=admin_headers
    )

    assert response.status_code == 422


def test_update_product_partially(client, create_product, admin_headers):
    product = create_product(name="Servomotor X1", price=Decimal("10.00"))

    response = client.put(
        f"/api/products/{product.id}",
        json={"price": "123.45", "stock": 7},
        headers=admin_headers,
    )

    assert response.status_code == 200, response.text
    data = response.json()
    assert Decimal(data["price"]) == Decimal("123.45")
    assert data["stock"] == 7
    assert data["name"] == "Servomotor X1"


def test_update_missing_product_returns_404(client, admin_headers):
    response = client.put("/api/products/9999", json={"stock": 1}, headers=admin_headers)

    assert response.status_code == 404


def test_delete_product_is_logical(client, create_product, admin_headers):
    product = create_product(name="Servomotor X1")

    response = client.delete(f"/api/products/{product.id}", headers=admin_headers)

    assert response.status_code == 204
    public = client.get(f"/api/products/{product.id}")
    assert public.status_code == 200
    assert public.json()["is_active"] is False
    listed = client.get("/api/products")
    assert listed.json() == []
    all_products = client.get("/api/products", params={"only_active": "false"})
    assert [p["id"] for p in all_products.json()] == [product.id]


def test_delete_missing_product_returns_404(client, admin_headers):
    response = client.delete("/api/products/9999", headers=admin_headers)

    assert response.status_code == 404


def test_cliente_cannot_delete_product(client, create_product, cliente_headers):
    product = create_product()

    response = client.delete(f"/api/products/{product.id}", headers=cliente_headers)

    assert response.status_code == 403


def test_product_price_uses_decimal(client, create_product):
    product = create_product(price=Decimal("19.99"))

    response = client.get(f"/api/products/{product.id}")

    assert response.status_code == 200
    assert Decimal(response.json()["price"]) == Decimal("19.99")
