---

name: diagram-gen
description: Generate technical diagrams using D2 language with structured templates
keywords:
  - diagram
  - architecture
  - flowchart
  - pipeline
  - sequence
  - topology
  - visualize
  - technical
  - diagrams
  - network
  - flow
  - design
  - draw

---

# Diagram Generator

Generate technical diagrams as PNG/SVG using D2 (terrastruct.com). D2 is a text-to-diagram tool with auto-layout, themes, and crisp rendering.

## Binary Location

```
"C:/Program Files/D2/d2.exe"
```

## Quick Command

```bash
"/c/Program Files/D2/d2.exe" --theme <THEME_ID> input.d2 output.png
```

## Workflow

1. Identify diagram type from user request
2. Write `.d2` file using the matching template below
3. Render: `"/c/Program Files/D2/d2.exe" --theme 200 input.d2 output.png`
4. Open result: `start "" "output.png"`

## Themes

| ID | Name | Use for |
|----|------|---------|
| 200 | Dark Mauve | Default - dark background, good contrast |
| 0 | Default | Light background |
| 1 | Neutral Grey | Light, minimal |
| 100 | Flagship Terrastruct | Colorful light |
| 300 | Terminal | Green-on-black terminal aesthetic |
| 301 | Terminal Grayscale | Grayscale terminal |

## Diagram Types & Templates

### 1. Architecture Diagram

For system components, services, infrastructure.

```d2
direction: right

title: System Name {
  shape: text
  near: top-center
  style.font-size: 24
  style.bold: true
}

# Group related components in containers
frontend: Frontend {
  style.fill: "#2d333b"
  style.stroke: "#539bf5"

  web: Web App { shape: rectangle }
  mobile: Mobile App { shape: rectangle }
}

backend: Backend {
  style.fill: "#2d333b"
  style.stroke: "#f39c12"

  api: API Gateway { shape: rectangle }
  worker: Worker { shape: rectangle }
}

data: Data Layer {
  style.fill: "#2d333b"
  style.stroke: "#2ecc71"

  db: PostgreSQL { shape: cylinder }
  cache: Redis { shape: cylinder }
}

frontend.web -> backend.api: HTTPS
frontend.mobile -> backend.api: HTTPS
backend.api -> data.db: SQL
backend.api -> data.cache: get/set
backend.worker -> data.db: batch write
```

### 2. Flow / Pipeline Diagram

For CI/CD, data pipelines, request flows.

```d2
direction: down

step1: "User submits prompt" { shape: rectangle }
step2: "Hook engine processes" { shape: rectangle }
step3: "Pattern match?" { shape: diamond }
step4: "Allow" { shape: circle; style.fill: "#2ecc71" }
step5: "Block + correct" { shape: hexagon; style.fill: "#e74c3c" }

step1 -> step2 -> step3
step3 -> step4: no match { style.stroke-dash: 3 }
step3 -> step5: match found
step5 -> step1: retry { style.stroke-dash: 3 }
```

### 3. Sequence Diagram

For request/response flows, API interactions.

```d2
shape: sequence_diagram

user: User
claude: Claude Code
hook: Stop Hook
files: "Stop/*.md"

user -> claude: prompt
claude -> claude: generate response
claude -> hook: response text
hook -> files: load instructions
hook -> hook: regex/keyword match
hook -> claude: block + correction {
  style.stroke: "#e74c3c"
}
claude -> claude: retry response
claude -> hook: new response
hook -> claude: allow {
  style.stroke: "#2ecc71"
  style.stroke-dash: 3
}
claude -> user: final response
```

### 4. Network / Topology Diagram

For infrastructure, network layouts.

```d2
direction: right

internet: Internet { shape: cloud }

vpc: "VPC 10.0.0.0/16" {
  style.fill: "#1c2128"

  public: "Public Subnet" {
    style.fill: "#2d333b"
    style.stroke: "#2ecc71"

    bastion: Bastion { shape: rectangle }
    nat: NAT GW { shape: rectangle }
  }

  private: "Private Subnet" {
    style.fill: "#2d333b"
    style.stroke: "#e74c3c"

    app: App Server { shape: rectangle }
    db: Database { shape: cylinder }
  }
}

internet -> vpc.public.bastion: SSH
internet -> vpc.public.nat: outbound
vpc.public.bastion -> vpc.private.app: SSH tunnel
vpc.public.nat -> vpc.private.app: internet access
vpc.private.app -> vpc.private.db: port 5432
```

### 5. Entity Relationship Diagram

For database schemas, data models.

```d2
user: User {
  shape: sql_table
  id: int {constraint: primary_key}
  name: varchar(255)
  email: varchar(255) {constraint: unique}
  created_at: timestamp
}

post: Post {
  shape: sql_table
  id: int {constraint: primary_key}
  title: varchar(255)
  body: text
  user_id: int {constraint: foreign_key}
  published: boolean
}

comment: Comment {
  shape: sql_table
  id: int {constraint: primary_key}
  body: text
  post_id: int {constraint: foreign_key}
  user_id: int {constraint: foreign_key}
}

user -> post: "1:many"
post -> comment: "1:many"
user -> comment: "1:many"
```

## D2 Shape Reference

| Shape | Use for |
|-------|---------|
| rectangle | Default component |
| circle | Status/state |
| diamond | Decision |
| hexagon | Process/action |
| cylinder | Database/storage |
| cloud | External service |
| queue | Message queue |
| package | Package/module |
| oval | Start/end |
| sql_table | DB table with columns |
| sequence_diagram | Set on root for sequence |

## Style Properties

```d2
style.fill: "#hex"          # Background color
style.stroke: "#hex"        # Border color
style.font-color: "#hex"    # Text color
style.stroke-dash: 3        # Dashed line
style.opacity: 0.5          # Transparency
style.bold: true             # Bold text
style.font-size: 24          # Font size
style.border-radius: 8       # Rounded corners
style.shadow: true           # Drop shadow
```

## Connection Styles

```d2
a -> b                       # Directed
a -- b                       # Undirected
a -> b: label                # Labeled
a -> b: label {
  style.stroke: "#e74c3c"   # Colored
  style.stroke-dash: 3      # Dashed
  style.animated: true       # Animated (SVG only)
}
```

## Output Formats

```bash
# PNG (default, recommended)
d2 input.d2 output.png

# SVG (supports animation)
d2 input.d2 output.svg

# PDF
d2 input.d2 output.pdf
```

## Tips

- Use `direction: right` for wide diagrams, `direction: down` for tall
- Group related items in containers (nested blocks)
- Use color-coded borders to distinguish component types
- Dashed lines for optional/async connections
- Always use theme 200 (Dark Mauve) unless user requests light theme
- Always open the output file after rendering
