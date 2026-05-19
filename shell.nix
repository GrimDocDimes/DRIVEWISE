{ pkgs ? import <nixpkgs> {} }:

pkgs.mkShell {
  buildInputs = with pkgs; [
    nodejs_20
    python312
    python312Packages.websockets
    python312Packages.numpy
    python312Packages.reportlab
  ];

  shellHook = ''
    echo "========================================"
    echo "  DRIVEWISE Development Shell"
    echo "  Node: $(node --version)"
    echo "  Python: $(python3 --version)"
    echo "========================================"
  '';
}
