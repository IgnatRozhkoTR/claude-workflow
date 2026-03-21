import sqlite3, json
from datetime import datetime
from db import DB_PATH

db = sqlite3.connect(str(DB_PATH))
db.row_factory = sqlite3.Row
db.execute("PRAGMA foreign_keys = ON")

# Step 1: find the workspace
rows = db.execute(
    'SELECT w.id, w.branch, w.phase, w.status, p.path FROM workspaces w JOIN projects p ON w.project_id = p.id'
).fetchall()

print("All workspaces:")
for r in rows:
    print(dict(r))

# Find the "test" branch workspace in the backend project
workspace_id = None
for r in rows:
    if r['branch'].lower() == 'test' and '/projects/backend' in r['path']:
        workspace_id = r['id']
        print(f"\nFound workspace ID: {workspace_id}")
        break

if workspace_id is None:
    print("\nWorkspace not found — trying any 'test' branch workspace")
    for r in rows:
        if r['branch'].lower() == 'test':
            workspace_id = r['id']
            print(f"Found workspace ID: {workspace_id}")
            break

if workspace_id is None:
    print("ERROR: No 'test' workspace found")
    db.close()
    exit(1)

# Step 2: build the plan
plan = {
    "description": "Backend API implementation with layered architecture",
    "systemDiagram": [
        {
            "title": "Class Diagram",
            "diagram": """classDiagram
    class User {
        +int id
        +String name
        +String email
        +authenticate()
    }
    class Order {
        +int id
        +User user
        +List~Product~ items
        +Decimal total
        +validate()
        +submit()
    }
    class Product {
        +int id
        +String name
        +Decimal price
        +int stock
    }
    class UserService {
        +createUser()
        +authenticate()
        +getProfile()
    }
    class OrderService {
        +createOrder()
        +validateStock()
        +calculateTotal()
    }
    class PaymentService {
        +processPayment()
        +refund()
    }
    UserService --> User
    OrderService --> Order
    OrderService --> Product
    OrderService --> PaymentService
    Order --> User
    Order --> Product"""
        },
        {
            "title": "Request Flow",
            "diagram": """sequenceDiagram
    participant Client
    participant AuthMiddleware
    participant UserController
    participant OrderController
    participant UserService
    participant OrderService
    participant PaymentService
    participant DB

    rect rgb(40, 40, 60)
    Note over Client,DB: Authentication Flow
    Client->>AuthMiddleware: POST /auth/login
    AuthMiddleware->>UserService: authenticate(credentials)
    UserService->>DB: SELECT user WHERE email=?
    DB-->>UserService: user row
    UserService-->>AuthMiddleware: JWT token
    AuthMiddleware-->>Client: 200 {token}
    end

    rect rgb(40, 60, 40)
    Note over Client,DB: Order Creation Flow
    Client->>OrderController: POST /orders {items}
    OrderController->>AuthMiddleware: validate token
    AuthMiddleware-->>OrderController: user context
    OrderController->>OrderService: createOrder(user, items)
    OrderService->>DB: SELECT stock FROM products
    DB-->>OrderService: stock levels
    OrderService->>OrderService: validateStock()
    OrderService->>OrderService: calculateTotal()
    OrderService->>PaymentService: processPayment(total)
    PaymentService-->>OrderService: payment confirmation
    OrderService->>DB: INSERT order
    DB-->>OrderService: order id
    OrderService-->>OrderController: order response
    OrderController-->>Client: 201 {order}
    end"""
        }
    ],
    "execution": [
        {
            "id": "3.1",
            "name": "Entity & Repository Layer",
            "tasks": [
                {"title": "User entity + repository", "files": ["src/models/user.py", "src/repositories/user_repo.py"], "agent": "middle-backend-engineer", "status": "pending", "group": "Entities"},
                {"title": "Order entity + repository", "files": ["src/models/order.py", "src/repositories/order_repo.py"], "agent": "middle-backend-engineer", "status": "pending", "group": "Entities"},
                {"title": "Product entity + repository", "files": ["src/models/product.py", "src/repositories/product_repo.py"], "agent": "middle-backend-engineer", "status": "pending", "group": "Entities"}
            ]
        },
        {
            "id": "3.2",
            "name": "Service Layer",
            "tasks": [
                {"title": "UserService with auth logic", "files": ["src/services/user_service.py"], "agent": "senior-backend-engineer", "status": "pending"},
                {"title": "OrderService with validation", "files": ["src/services/order_service.py"], "agent": "middle-backend-engineer", "status": "pending"},
                {"title": "PaymentService integration", "files": ["src/services/payment_service.py"], "agent": "senior-backend-engineer", "status": "pending"}
            ]
        },
        {
            "id": "3.3",
            "name": "API Controllers",
            "tasks": [
                {"title": "User endpoints (CRUD + auth)", "files": ["src/controllers/user_controller.py"], "agent": "middle-backend-engineer", "status": "pending", "group": "Controllers"},
                {"title": "Order endpoints", "files": ["src/controllers/order_controller.py"], "agent": "junior-backend-engineer", "status": "pending", "group": "Controllers"}
            ]
        },
        {
            "id": "3.4",
            "name": "Integration Tests",
            "tasks": [
                {"title": "User flow integration tests", "files": ["tests/test_user_flow.py"], "agent": "middle-backend-test-engineer", "status": "pending", "group": "Flow Tests"},
                {"title": "Order flow integration tests", "files": ["tests/test_order_flow.py"], "agent": "middle-backend-test-engineer", "status": "pending", "group": "Flow Tests"},
                {"title": "E2E payment tests", "files": ["tests/test_payment_e2e.py"], "agent": "senior-backend-test-engineer", "status": "pending"},
                {"title": "Load test configuration", "files": ["tests/locustfile.py"], "agent": "junior-backend-engineer", "status": "pending"}
            ]
        }
    ]
}

scope = {
    "3.1": {"must": ["src/models/", "src/repositories/"], "may": ["src/config/"]},
    "3.2": {"must": ["src/services/"], "may": ["src/utils/"]},
    "3.3": {"must": ["src/controllers/"], "may": ["src/middleware/"]},
    "3.4": {"must": ["tests/"], "may": []}
}

# Step 3: update the workspace
db.execute(
    "UPDATE workspaces SET plan_json = ?, plan_status = 'pending', phase = '2.0', scope_json = ? WHERE id = ?",
    (json.dumps(plan), json.dumps(scope), workspace_id)
)

# Step 4: insert phase_history entry
db.execute(
    "INSERT INTO phase_history (workspace_id, from_phase, to_phase, time) VALUES (?, '0', '2.0', ?)",
    (workspace_id, datetime.now().isoformat())
)

db.commit()
db.close()
print("\nDone — plan set, phase set to 2.0, phase_history entry inserted.")
