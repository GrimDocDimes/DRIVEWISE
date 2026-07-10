{ pkgs ? import <nixpkgs> {} }:

pkgs.mkShell {
  buildInputs = with pkgs; [
    # --- Existing ---
    nodejs_20
    python312
    python312Packages.websockets
    python312Packages.numpy
    python312Packages.reportlab

    # --- Phase 1: Persistence layer (added) ---
    postgresql                          # pg_config + optional local PG server
    python312Packages.sqlalchemy
    python312Packages.psycopg2          # PostgreSQL driver (falls back to SQLite gracefully)

    # --- Phase 2/3: Agent + API (added) ---
    python312Packages.fastapi
    python312Packages.uvicorn
    python312Packages.anthropic
    python312Packages.pandas

    # --- Dev utility (added) ---
    python312Packages.python-dotenv     # .env file support for ANTHROPIC_API_KEY
  ];

  shellHook = ''
    echo "========================================"
    echo "  DRIVEWISE Development Shell"
    echo "  Node: $(node --version)"
    echo "  Python: $(python3 --version)"
    echo "========================================"
  '';
}
