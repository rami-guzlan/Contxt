---
id: system-scopes
title: Scopes and partitions
keywords: scope chain company department person partition client project admission access
---
Scopes form an inheritance tree declared in `brain.json` (`company > dept:x > person:y`). A
caller sees notes whose scope is on its chain; the closest scope wins. Partitions (clients,
projects) are a sealed second axis: a request activates at most one, a partitioned note is
visible only while its partition is active, and only to a chain that owns the partition, so
two clients never share a packet. Admission happens before any relevance scoring.
