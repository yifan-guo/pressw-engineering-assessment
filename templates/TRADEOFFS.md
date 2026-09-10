# Trade-offs

- **Built vs. scoped:** what got cut under time pressure

scoped: 
de-scoped: assignments, shifts, background job was cut

- **Specific trade-offs and why**

- **What you'd do next with more time**

Update crew update endpoint to complete the migration of the crew 
Probe the remainder of the system

- **Known issues or unhandled cases**
Callers might observe stale crew data because write and read ownership is split across systems. This is resolved once crew/update is migrated

routes.yaml must explicitly route only crew actions by very (show, list -> Encore, update -> Callback)

- **Post-window commits, if any**
N/A
