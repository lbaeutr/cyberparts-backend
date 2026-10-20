from decimal import Decimal

from app.models.enums import RoleName


def order_payload(*items):
    return {"items": [{"product_id": product_id, "quantity": quantity} for product_id, quantity in items]}


def test_create_order_computes_total_and_decrements_stock(client, cliente_headers, create_product, db):
    product = create_product(price=Decimal("10.50"), stock=5)

    response = client.post(
        "/api/orders",
        json=order_payload((product.id, 2)),
        headers=cliente_headers,
    )

    assert response.status_code == 201, response.text
    data = response.json()
    assert data["status"] == "PENDING"
    assert Decimal(data["total"]) == Decimal("21.00")
    assert data["items"][0]["quantity"] == 2
    assert Decimal(data["items"][0]["unit_price"]) == Decimal("10.50")
    db.refresh(product)
    assert product.stock == 3


def test_create_order_with_multiple_items(client, cliente_headers, create_product):
    first = create_product(name="Servo", price=Decimal("10.00"), stock=5)
    second = create_product(name="Sensor", price=Decimal("5.25"), stock=5)

    response = client.post(
        "/api/orders",
        json=order_payload((first.id, 2), (second.id, 1)),
        headers=cliente_headers,
    )

    assert response.status_code == 201, response.text
    assert Decimal(response.json()["total"]) == Decimal("25.25")
    assert len(response.json()["items"]) == 2


def test_create_order_with_insufficient_stock_returns_409(client, cliente_headers, create_product):
    product = create_product(stock=1)

    response = client.post(
        "/api/orders",
        json=order_payload((product.id, 2)),
        headers=cliente_headers,
    )

    assert response.status_code == 409


def test_create_order_with_inactive_product_returns_404(client, cliente_headers, create_product):
    product = create_product(is_active=False)

    response = client.post(
        "/api/orders",
        json=order_payload((product.id, 1)),
        headers=cliente_headers,
    )

    assert response.status_code == 404


def test_create_order_with_missing_product_returns_404(client, cliente_headers):
    response = client.post(
        "/api/orders",
        json=order_payload((9999, 1)),
        headers=cliente_headers,
    )

    assert response.status_code == 404


def test_create_order_requires_authentication(client, create_product):
    product = create_product()

    response = client.post("/api/orders", json=order_payload((product.id, 1)))

    assert response.status_code == 401


def test_create_order_validation_errors(client, cliente_headers, create_product):
    product = create_product()

    empty = client.post("/api/orders", json={"items": []}, headers=cliente_headers)
    zero = client.post(
        "/api/orders",
        json=order_payload((product.id, 0)),
        headers=cliente_headers,
    )

    assert empty.status_code == 422
    assert zero.status_code == 422


def test_cliente_only_sees_own_orders(client, create_product, create_user, login, cliente_headers):
    product = create_product(stock=10)
    client.post("/api/orders", json=order_payload((product.id, 1)), headers=cliente_headers)
    other = create_user("otro_cliente", RoleName.CLIENTE)
    other_headers = login(other.username)
    client.post("/api/orders", json=order_payload((product.id, 1)), headers=other_headers)

    response = client.get("/api/orders", headers=cliente_headers)

    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["user_id"] != other.id


def test_staff_sees_all_orders(client, create_product, create_user, login, cliente_headers, admin_headers):
    product = create_product(stock=10)
    client.post("/api/orders", json=order_payload((product.id, 1)), headers=cliente_headers)
    other = create_user("otro_cliente", RoleName.CLIENTE)
    other_headers = login(other.username)
    client.post("/api/orders", json=order_payload((product.id, 1)), headers=other_headers)

    response = client.get("/api/orders", headers=admin_headers)

    assert response.status_code == 200
    assert len(response.json()) == 2


def test_cliente_cannot_read_other_users_order(
    client, create_product, create_user, login, cliente_headers
):
    product = create_product(stock=10)
    other = create_user("otro_cliente", RoleName.CLIENTE)
    other_headers = login(other.username)
    created = client.post(
        "/api/orders", json=order_payload((product.id, 1)), headers=other_headers
    )
    order_id = created.json()["id"]

    response = client.get(f"/api/orders/{order_id}", headers=cliente_headers)

    assert response.status_code == 403


def test_staff_can_read_any_order(client, create_product, cliente_headers, admin_headers):
    product = create_product()
    created = client.post(
        "/api/orders", json=order_payload((product.id, 1)), headers=cliente_headers
    )

    response = client.get(f"/api/orders/{created.json()['id']}", headers=admin_headers)

    assert response.status_code == 200


def test_get_missing_order_returns_404(client, cliente_headers):
    response = client.get("/api/orders/9999", headers=cliente_headers)

    assert response.status_code == 404


def test_staff_can_update_order_status(client, create_product, cliente_headers, gestor_headers):
    product = create_product()
    created = client.post(
        "/api/orders", json=order_payload((product.id, 1)), headers=cliente_headers
    )

    response = client.patch(
        f"/api/orders/{created.json()['id']}/status",
        json={"status": "PAID"},
        headers=gestor_headers,
    )

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "PAID"


def test_cliente_cannot_update_order_status(client, create_product, cliente_headers):
    product = create_product()
    created = client.post(
        "/api/orders", json=order_payload((product.id, 1)), headers=cliente_headers
    )

    response = client.patch(
        f"/api/orders/{created.json()['id']}/status",
        json={"status": "PAID"},
        headers=cliente_headers,
    )

    assert response.status_code == 403


def test_invalid_order_status_returns_422(client, create_product, cliente_headers, admin_headers):
    product = create_product()
    created = client.post(
        "/api/orders", json=order_payload((product.id, 1)), headers=cliente_headers
    )

    response = client.patch(
        f"/api/orders/{created.json()['id']}/status",
        json={"status": "ENVIADO"},
        headers=admin_headers,
    )

    assert response.status_code == 422


def test_update_missing_order_returns_404(client, admin_headers):
    response = client.patch(
        "/api/orders/9999/status", json={"status": "PAID"}, headers=admin_headers
    )

    assert response.status_code == 404


def test_cancelling_order_restores_stock(client, create_product, cliente_headers, admin_headers, db):
    product = create_product(stock=10)
    created = client.post(
        "/api/orders", json=order_payload((product.id, 3)), headers=cliente_headers
    )
    order_id = created.json()["id"]
    db.refresh(product)
    assert product.stock == 7

    cancelled = client.patch(
        f"/api/orders/{order_id}/status",
        json={"status": "CANCELLED"},
        headers=admin_headers,
    )
    db.refresh(product)
    assert cancelled.status_code == 200
    assert product.stock == 10

    client.patch(
        f"/api/orders/{order_id}/status",
        json={"status": "CANCELLED"},
        headers=admin_headers,
    )
    db.refresh(product)
    assert product.stock == 10


def test_failed_order_does_not_modify_stock(client, cliente_headers, create_product, db):
    product = create_product(stock=2)

    response = client.post(
        "/api/orders", json=order_payload((product.id, 3)), headers=cliente_headers
    )

    assert response.status_code == 409
    db.refresh(product)
    assert product.stock == 2


def test_duplicate_products_are_aggregated(client, cliente_headers, create_product, db):
    product = create_product(price=Decimal("10.00"), stock=5)

    response = client.post(
        "/api/orders",
        json=order_payload((product.id, 2), (product.id, 2)),
        headers=cliente_headers,
    )

    assert response.status_code == 201, response.text
    data = response.json()
    assert len(data["items"]) == 1
    assert data["items"][0]["quantity"] == 4
    assert Decimal(data["total"]) == Decimal("40.00")
    db.refresh(product)
    assert product.stock == 1


def test_duplicate_products_insufficient_stock_returns_409(
    client, cliente_headers, create_product, db
):
    product = create_product(stock=3)

    response = client.post(
        "/api/orders",
        json=order_payload((product.id, 2), (product.id, 2)),
        headers=cliente_headers,
    )

    assert response.status_code == 409
    db.refresh(product)
    assert product.stock == 3


def test_invalid_status_transition_returns_409(
    client, create_product, cliente_headers, admin_headers
):
    product = create_product(stock=5)
    created = client.post(
        "/api/orders", json=order_payload((product.id, 1)), headers=cliente_headers
    )
    order_id = created.json()["id"]
    paid = client.patch(
        f"/api/orders/{order_id}/status", json={"status": "PAID"}, headers=admin_headers
    )
    assert paid.status_code == 200

    response = client.patch(
        f"/api/orders/{order_id}/status",
        json={"status": "PENDING"},
        headers=admin_headers,
    )

    assert response.status_code == 409
    assert "no permitida" in response.json()["detail"]


def test_delivered_order_cannot_be_cancelled_and_keeps_stock(
    client, create_product, cliente_headers, admin_headers, db
):
    product = create_product(stock=5)
    created = client.post(
        "/api/orders", json=order_payload((product.id, 2)), headers=cliente_headers
    )
    order_id = created.json()["id"]

    for new_status in ("PAID", "SHIPPED", "DELIVERED"):
        updated = client.patch(
            f"/api/orders/{order_id}/status",
            json={"status": new_status},
            headers=admin_headers,
        )
        assert updated.status_code == 200, updated.text

    db.refresh(product)
    assert product.stock == 3

    response = client.patch(
        f"/api/orders/{order_id}/status",
        json={"status": "CANCELLED"},
        headers=admin_headers,
    )

    assert response.status_code == 409
    db.refresh(product)
    assert product.stock == 3


def test_cancelled_order_cannot_be_reopened(
    client, create_product, cliente_headers, admin_headers
):
    product = create_product(stock=5)
    created = client.post(
        "/api/orders", json=order_payload((product.id, 1)), headers=cliente_headers
    )
    order_id = created.json()["id"]

    cancelled = client.patch(
        f"/api/orders/{order_id}/status",
        json={"status": "CANCELLED"},
        headers=admin_headers,
    )
    assert cancelled.status_code == 200

    response = client.patch(
        f"/api/orders/{order_id}/status", json={"status": "PAID"}, headers=admin_headers
    )

    assert response.status_code == 409


def test_list_orders_filters_by_status(client, create_product, cliente_headers, admin_headers):
    product = create_product(stock=10)
    pending = client.post(
        "/api/orders", json=order_payload((product.id, 1)), headers=cliente_headers
    ).json()
    paid = client.post(
        "/api/orders", json=order_payload((product.id, 1)), headers=cliente_headers
    ).json()
    client.patch(
        f"/api/orders/{paid['id']}/status", json={"status": "PAID"}, headers=admin_headers
    )

    response = client.get("/api/orders?status=PAID", headers=cliente_headers)

    assert response.status_code == 200, response.text
    ids = [order["id"] for order in response.json()]
    assert ids == [paid["id"]]
    assert pending["id"] not in ids


def test_list_orders_paginates(client, create_product, cliente_headers):
    product = create_product(stock=10)
    for _ in range(3):
        client.post("/api/orders", json=order_payload((product.id, 1)), headers=cliente_headers)

    first_page = client.get("/api/orders?limit=2", headers=cliente_headers)
    second_page = client.get("/api/orders?skip=2&limit=2", headers=cliente_headers)

    assert first_page.status_code == 200, first_page.text
    assert len(first_page.json()) == 2
    assert len(second_page.json()) == 1
    assert {order["id"] for order in first_page.json()}.isdisjoint(
        {order["id"] for order in second_page.json()}
    )


def test_order_payload_includes_product_and_user_names(client, create_product, cliente_headers):
    product = create_product(name="Servo Z", price=Decimal("8.00"), stock=3)
    created = client.post(
        "/api/orders", json=order_payload((product.id, 1)), headers=cliente_headers
    )
    assert created.status_code == 201, created.text

    order = client.get(f"/api/orders/{created.json()['id']}", headers=cliente_headers).json()

    assert order["username"] == "cliente_test"
    assert order["items"][0]["product_name"] == "Servo Z"
