<script lang="ts">
  let { status }: { status: string } = $props();
</script>

<span class="pill" data-status={status.toLowerCase()}>{status}</span>

<style>
  .pill {
    display: inline-flex;
    align-items: center;
    min-height: 1.75rem;
    padding: 0 0.65rem;
    border-radius: 999px;
    border: 1px solid rgba(148, 163, 184, 0.22);
    background: rgba(148, 163, 184, 0.12);
    color: var(--muted-strong);
    font-size: 0.82rem;
    font-weight: 700;
    text-transform: capitalize;
  }

  .pill[data-status='connected'],
  .pill[data-status='online'],
  .pill[data-status='ok'] {
    border-color: rgba(45, 212, 191, 0.35);
    background: rgba(45, 212, 191, 0.14);
    color: #99f6e4;
  }

  .pill[data-status='error'],
  .pill[data-status='offline'],
  .pill[data-status='failed'] {
    border-color: rgba(251, 113, 133, 0.35);
    background: rgba(251, 113, 133, 0.14);
    color: #fecdd3;
  }

  .pill[data-status='connecting'],
  .pill[data-status='reconnecting'],
  .pill[data-status='queued'] {
    border-color: rgba(250, 204, 21, 0.38);
    background: rgba(250, 204, 21, 0.14);
    color: #fde68a;
  }
</style>
