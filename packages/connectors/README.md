# workspace-connectors

Adapters at the edges of the workspace, behind documented interfaces so community
contributions never fork the core:

- **Providers** describe how a model platform connects: the MCP configuration it needs and
  the worker prompt its scheduled check runs. They never execute models.
- **Destinations** receive approved artifacts. Each declares the artifact types it accepts;
  the core only offers a destination for an approved version, and records the export.
