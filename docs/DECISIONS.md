# Implementation Decisions

- Group room limits default to 50 members and are configurable with
  `MAX_GROUP_MEMBERS`.
- Group history visibility is enforced with `Membership.joined_sequence_id`.
- File uploads use a local `server/data/uploads` directory for development;
  deployment uses external object storage because Render disks are ephemeral.
- The Electron client keeps Socket.IO in the main process and exposes only
  typed IPC operations through preload.
- Deployment keeps CORS origins, trusted proxy mode, and upload storage
  configuration in environment variables.
- Electron Windows packaging uses electron-builder's portable ZIP target in
  this workspace: NSIS failed in the local environment while memory-mapping a
  127 MB archive. The ZIP target contains the packaged app without requiring
  an installer compiler; a release pipeline with sufficient memory can switch
  back to NSIS.