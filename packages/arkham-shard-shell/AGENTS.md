# SHARD SHELL KNOWLEDGE BASE

## OVERVIEW
Unified React/TypeScript UI shell that dynamically renders shard interfaces based on backend manifests.

## STRUCTURE
- `src/components/layout/`: Core UI framework (Shell, Sidebar, TopBar, ContentArea)
- `src/components/generic/`: Data-driven rendering (GenericList, GenericForm)
- `src/components/common/`: Shared UI atoms (Icon, ShardErrorBoundary, LoadingSkeleton)
- `src/context/`: Global state providers (Shell, Project, Auth, Toast, Confirm)
- `src/hooks/`: Reactive utilities (useUrlParams, useFetch, useBadges)
- `src/pages/`: Specific shard UI implementations and catch-all generic renderer

## WHERE TO LOOK
- **Entry Point**: `src/main.tsx` (DOM mount) and `src/App.tsx` (Provider stack and Routing)
- **Dynamic Navigation**: `src/context/ShellContext.tsx` (manifest fetching) and `src/components/layout/Sidebar.tsx` (rendering)
- **Generic Rendering**: `src/pages/generic/GenericShardPage.tsx` (fallback logic)
- **URL State**: `src/hooks/useUrlParams.ts` (flat param synchronization)
- **Layout Engine**: `src/components/layout/Shell.tsx` (overall grid and responsiveness)
- **Icon System**: `src/components/common/Icon.tsx` (dynamic Lucide loader)
- **Global Types**: `src/types/index.ts` (ShardManifest, UIConfig)
- **API Client**: `src/utils/api.ts` and `src/hooks/useFetch.ts` (request signing and error handling)

## CODE MAP
| Symbol | Type | Location | Role |
|--------|------|----------|------|
| `ShellProvider` | Context | `src/context/ShellContext.tsx` | State owner for navigation and manifests |
| `GenericShardPage` | Component | `src/pages/generic/GenericShardPage.tsx` | Dynamic fallback for shards without custom UI |
| `useUrlParams` | Hook | `src/hooks/useUrlParams.ts` | Bi-directional URL state synchronization |
| `Sidebar` | Component | `src/components/layout/Sidebar.tsx` | Multi-level collapsible navigation tree |
| `GenericList` | Component | `src/components/generic/GenericList.tsx` | Data table with filtering, pagination, and actions |
| `Icon` | Component | `src/components/common/Icon.tsx` | String-to-component mapping for Lucide icons |
| `useFetch` | Hook | `src/hooks/useFetch.ts` | Standardized data fetching with error surfacing |
| `ProjectProvider` | Context | `src/context/ProjectContext.tsx` | Global project scope and tenant management |

## UI RENDERING FLOW
1. **Boot**: `ShellProvider` fetches all active shard manifests from `/api/shards/` on mount.
2. **Nav Build**: `Sidebar` groups shards by `navigation.category` and sorts by `navigation.order`.
3. **Route Match**: `App.tsx` routes map paths to specific shard pages.
4. **Fallback**: Routes not explicitly defined fall through to `GenericShardPage`.
5. **Generic Render**: `GenericShardPage` uses `ui` config (columns, endpoints) from the manifest to render `GenericList`.
6. **Interaction**: `GenericList` triggers `GenericForm` in dialogs for CRUD operations based on manifest actions.
7. **Synchronization**: State changes (filters, page) are pushed to the URL via `useUrlParams`.

## CONVENTIONS
- **Flat URL State**: Use `useUrlParams` for all page state (filters, search, IDs). Avoid nested objects in URL.
- **Dynamic Icons**: Use `<Icon name="LucideName" />` to load icons by string name from manifests.
- **Isolation**: Shard pages must not import from other shard pages. Use `ShellContext` for cross-shard navigation.
- **Air-Gap Safe**: All fonts and assets are local. No external CDN requests permitted.
- **Type Safety**: Use `ShardManifest` type for all shard-related data. Do not use `any`.
- **CSS Modules**: Use sibling `.css` files with identical names for component-specific styles.
- **Error Boundaries**: Wrap complex shard visualizations in `ShardErrorBoundary` to prevent total shell crashes.

## ANTI-PATTERNS
- **Hardcoded Navigation**: Never add shard links manually to the sidebar; use the manifest `navigation` block.
- **Business Logic**: Keep shell pages thin. Logic belongs in backend services or specialized shard hooks.
- **Direct LocalStorage**: Use `useLocalState` hook for persistence to ensure consistent prefixing and serialization.
- **Prop Drilling**: Use specialized contexts (Toast, Confirm, Project) for cross-cutting concerns.
