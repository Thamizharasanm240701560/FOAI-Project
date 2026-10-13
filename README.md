# ⚡ AI Power Optimizer

**Intelligent Household Backup Power Management using Simulated Annealing**

---

## 📋 Project Information

| Field | Value |
|-------|-------|
| **Project Name** | AI Power Optimizer |
| **Domain** | Artificial Intelligence — Local Search and Optimization |
| **FOAI Unit** | Unit II — Problem Solving |
| **Main Algorithm** | Simulated Annealing |
| **Application** | Smart Energy Management during Power Outages |

---

## 🎯 Problem Statement

During a power outage, a household may have limited backup power from an inverter, battery, or UPS system. The available backup power cannot operate every appliance simultaneously.

**The AI agent must determine:**
- Which appliances should be ON or OFF
- When each appliance should operate
- How long each appliance should operate
- How to prioritize essential appliances
- How to avoid exceeding inverter power capacity
- How to conserve battery energy for the outage duration

This is a **combinatorial optimization problem** with constraints — the perfect use case for **Simulated Annealing**, a local search algorithm from FOAI Unit II.

---

## 🧠 FOAI Syllabus Mapping

### Unit I — Introduction to Artificial Intelligence

| Concept | Implementation |
|---------|---------------|
| **Intelligent Agent** | The Power Optimizer acts as a rational agent that observes the environment (battery, appliances, constraints) and produces optimal actions (appliance schedule) |
| **Agent and Environment** | Environment = battery state, inverter capacity, appliance data. Agent = SA optimizer |
| **Rational Behaviour** | The agent maximizes a fitness function (utility) while respecting constraints |
| **Problem-Solving Agent** | Formulated as a search problem: find the schedule that maximizes fitness |

### Unit II — Problem Solving (Core Unit)

| Concept | Implementation |
|---------|---------------|
| **Local Search** | SA maintains ONE current state and explores neighbors — no search tree |
| **Optimization** | Maximizing the fitness function (weighted priority + duration + energy) |
| **Simulated Annealing** | The main algorithm — see detailed explanation below |
| **State Space** | All possible ON/OFF schedules: 2^(appliances × time_slots) states |
| **State Representation** | 2D binary matrix `schedule[appliance][slot]` ∈ {0, 1} |
| **Neighbor State** | Small random change: toggle, move, extend, reduce, or swap |
| **Objective Function** | Fitness function combining rewards and penalties |
| **Heuristic Evaluation** | Priority weights guide the fitness calculation |

### Unit III — Not required for core implementation

_(Game playing and CSP concepts are not part of this project's optimization pipeline.)_

### Unit IV — Not required for core implementation

_(Logical reasoning concepts are not used in the optimization engine.)_

---

## ⚙️ Simulated Annealing — Detailed Explanation

### What is Simulated Annealing?

Simulated Annealing is a **local search optimization algorithm** inspired by the metallurgical process of annealing, where a material is heated and then slowly cooled to reach a low-energy crystalline state.

### How it works in this project:

```
1. Generate an INITIAL STATE (random feasible schedule)
2. Set TEMPERATURE T = T₀ (e.g., 1000)
3. Calculate FITNESS of current state

4. REPEAT while T > T_min and iteration < max_iterations:
   a. Generate NEIGHBOR (small random change to schedule)
   b. Calculate FITNESS of neighbor
   c. Calculate ΔE = neighbor_fitness − current_fitness

   d. IF ΔE > 0:
        Accept neighbor (it's better)
      ELSE:
        Calculate P = exp(ΔE / T)
        Accept with probability P
        (allows escaping local optima)

   e. Update BEST SOLUTION if current is the best ever

   f. COOL: T = T × α (e.g., T = T × 0.95)
   g. Increment iteration

5. RETURN best solution found
```

### Key Parameters

| Parameter | Symbol | Default | Purpose |
|-----------|--------|---------|---------|
| Initial Temperature | T₀ | 1000 | Controls initial exploration intensity |
| Minimum Temperature | T_min | 0.1 | Stopping condition |
| Cooling Rate | α | 0.95 | How fast temperature decreases |
| Max Iterations | — | 10,000 | Upper bound on search steps |

### Acceptance Probability Formula

```
P = exp(ΔE / T)

where:
  ΔE = new_fitness - current_fitness  (negative when neighbor is worse)
  T  = current temperature

At high T:  P ≈ 1  →  worse solutions often accepted (EXPLORATION)
At low  T:  P ≈ 0  →  only improvements accepted (EXPLOITATION)
```

### Why Simulated Annealing?

1. **Exponential state space**: With 6 appliances and 8 time slots, there are 2^48 ≈ 281 trillion possible schedules. Exhaustive search is impossible.

2. **Escapes local optima**: Unlike greedy/hill-climbing, SA can accept worse solutions temporarily, allowing it to escape local optima and find better global solutions.

3. **No gradient needed**: SA works with any fitness function — it doesn't need derivatives or convexity.

4. **Memory efficient**: SA maintains only ONE state at a time (unlike genetic algorithms that need populations).

5. **Simple to implement**: The algorithm is straightforward enough to explain in a viva.

---

## 📊 Fitness Function

```
Fitness = Priority Reward
        + Essential Appliance Reward
        + Duration Satisfaction Reward
        + Time Preference Reward
        + Energy Utilization Reward
        − Power Violation Penalty      (HARD CONSTRAINT)
        − Energy Violation Penalty     (HARD CONSTRAINT)
        − Switching Penalty
        − Essential Violation Penalty  (HARD CONSTRAINT)
```

| Component | Formula | Weight |
|-----------|---------|--------|
| Priority Reward | Σ (priority_weight × slots_on × power/100) | VERY_HIGH=10, HIGH=7, MEDIUM=4, LOW=1 |
| Essential Reward | Σ (50 × slots_on) for essential appliances | 50 per slot |
| Duration Satisfaction | min(actual/required, 1.0) × 30 × priority_weight | 30 |
| Time Preference | (slots_in_window / total_slots) × 15 × priority_weight | 15 |
| Energy Utilization | Bonus for 60-90% utilization | 10 |
| Power Violation | −10000 × (1 + excess_ratio) per violating slot | −10000 |
| Energy Violation | −5000 × (1 + excess_ratio) | −5000 |
| Switching Penalty | −2 × transitions per appliance | −2 |
| Essential Violation | −8000 × (1 + shortfall_ratio) | −8000 |

---

## 🔒 Constraints

| # | Constraint | Description |
|---|-----------|-------------|
| C1 | **Power** | Per-slot total power ≤ max inverter power |
| C2 | **Energy** | Total energy consumed ≤ available battery energy |
| C3 | **Essential** | Essential appliances must meet minimum operating duration |
| C4 | **Time Window** | Appliances only operate within their preferred time window |
| C5 | **Max Duration** | Appliances cannot exceed their maximum allowed duration |

---

## 🏗️ Architecture

```
USER
 ↓
INPUT INTERFACE (HTML/CSS/JS)
 ↓
APPLIANCE + BATTERY DATA (JSON)
 ↓
DATA VALIDATION (Pydantic)
 ↓
CONSTRAINT CHECKER (constraints.py)
 ↓
SIMULATED ANNEALING ENGINE (simulated_annealing.py)
 ├── Initial State Generator (scheduler.py)
 ├── Neighbor Generator (neighbor.py)
 ├── Fitness Evaluator (fitness.py)
 └── Best Solution Tracker
 ↓
OPTIMIZED POWER SCHEDULE
 ↓
DASHBOARD (Charts, Gantt, Comparison)
```

---

## 🛠️ Technology Stack

| Component | Technology |
|-----------|-----------|
| Frontend | HTML, CSS, JavaScript |
| Backend | Python, FastAPI |
| Charts | Chart.js v4 |
| Optimization | Hand-implemented Simulated Annealing |
| Data | JSON (no database) |

**No external optimization libraries** (no OR-Tools, PuLP, SciPy optimize, etc.)

---

## 📁 Project Structure

```
power-optimizer-ai/
├── backend/
│   ├── app.py                          # FastAPI application + endpoints
│   ├── optimizer/
│   │   ├── simulated_annealing.py      # Core SA algorithm
│   │   ├── fitness.py                  # Fitness/objective function
│   │   ├── constraints.py             # Hard constraint validators
│   │   ├── neighbor.py                 # Neighbor generation (6 operators)
│   │   └── scheduler.py               # Initial solution + naive baseline
│   ├── models/
│   │   └── appliance.py               # Pydantic data models
│   └── data/
│       └── default_appliances.json     # Default appliances + demo
├── frontend/
│   ├── index.html                      # Dashboard UI
│   ├── style.css                       # Dark glassmorphism theme
│   └── script.js                       # UI logic + Chart.js charts
├── tests/
│   ├── test_optimizer.py               # SA algorithm tests
│   ├── test_constraints.py             # Constraint tests
│   └── test_fitness.py                 # Fitness function tests
├── README.md                           # This file
├── requirements.txt                    # Python dependencies
└── .gitignore
```

---

## 🚀 Installation & Running

### Prerequisites
- Python 3.8+ installed
- pip package manager

### Setup

```bash
# Navigate to project directory
cd power-optimizer-ai

# Create virtual environment (recommended)
python -m venv venv
venv\Scripts\activate       # Windows
# source venv/bin/activate  # Mac/Linux

# Install dependencies
pip install -r requirements.txt
```

### Run the Application

```bash
python backend/app.py
```

Then open **http://localhost:8000** in your browser.

### Run Tests

```bash
# All tests
python tests/test_constraints.py
python tests/test_fitness.py
python tests/test_optimizer.py
```

---

## 🌐 API Documentation

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/health` | GET | Health check |
| `/api/default-appliances` | GET | Default appliances + demo scenario |
| `/api/validate` | POST | Validate input without optimization |
| `/api/optimize` | POST | Run Simulated Annealing and return results |

### POST /api/optimize — Request Body

```json
{
  "backup": {
    "max_power_watts": 1000,
    "battery_capacity_wh": 3000,
    "battery_percentage": 70,
    "outage_duration_hours": 4,
    "solar_enabled": false
  },
  "appliances": [
    {
      "name": "Refrigerator",
      "power_watts": 150,
      "priority": "VERY_HIGH",
      "required_duration_hours": 3,
      "min_duration_hours": 2,
      "max_duration_hours": 4,
      "is_essential": true
    }
  ],
  "settings": {
    "initial_temperature": 1000,
    "min_temperature": 0.1,
    "cooling_rate": 0.95,
    "max_iterations": 10000,
    "time_slot_minutes": 30
  }
}
```

### Response (abbreviated)

```json
{
  "schedule": [...],
  "fitness": 1234.5,
  "energy_consumed_wh": 1500,
  "remaining_energy_wh": 600,
  "battery_percentage": 20.0,
  "peak_power_watts": 985,
  "priority_satisfaction": 92.5,
  "essential_satisfaction": 100.0,
  "sa_metrics": {
    "initial_temperature": 1000,
    "final_temperature": 0.08,
    "total_iterations": 10000,
    "accepted_count": 6234,
    "best_fitness": 1234.5,
    "fitness_history": [...]
  }
}
```

---

## 📋 Demo Scenario

| Parameter | Value |
|-----------|-------|
| Max Inverter Power | 1000 W |
| Battery Capacity | 3000 Wh |
| Battery Percentage | 70% |
| Available Energy | 2100 Wh |
| Outage Duration | 4 hours |

| Appliance | Power | Priority | Essential |
|-----------|-------|----------|-----------|
| Refrigerator | 150 W | Very High | ✅ |
| Wi-Fi Router | 10 W | High | ✅ |
| Fan | 75 W | High | ❌ |
| Television | 120 W | Medium | ❌ |
| Water Pump | 750 W | Medium | ❌ |
| Air Conditioner | 1200 W | Low | ❌ |

**Expected Result:** The AC (1200W) cannot be scheduled because it exceeds the 1000W inverter capacity. The Water Pump (750W) can only operate when few other appliances are running.

---

## 🔑 Key Files for Viva Explanation

| File | What to Explain |
|------|----------------|
| `simulated_annealing.py` | The core SA loop — initial state, neighbor, acceptance probability, cooling |
| `fitness.py` | How the objective function rewards and penalizes schedules |
| `constraints.py` | The five hard constraints and how they are checked |
| `neighbor.py` | Six mutation operators for generating neighbor states |
| `scheduler.py` | How the initial state is generated |

---

## 🔮 Future Enhancements

- Real-time battery monitoring integration
- Multiple backup source management
- Weather-based solar prediction
- Mobile application interface
- Multi-day outage planning
- Appliance usage learning
