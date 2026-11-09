-- Additive indexes for dashboard, notification, and resource-request queries.
-- Safe to run more than once; this script does not alter application records.
CREATE INDEX IF NOT EXISTS ix_help_requests_seeker_created
    ON public.help_requests(seeker_id, created_at);
CREATE INDEX IF NOT EXISTS ix_help_requests_volunteer_updated
    ON public.help_requests(assigned_volunteer_id, updated_at);
CREATE INDEX IF NOT EXISTS ix_resource_listings_donor_created
    ON public.resource_listings(donor_id, created_at);
CREATE INDEX IF NOT EXISTS ix_resource_listings_status_created
    ON public.resource_listings(status, created_at);
CREATE INDEX IF NOT EXISTS ix_resource_requests_volunteer_updated
    ON public.resource_requests(volunteer_id, updated_at);
CREATE INDEX IF NOT EXISTS ix_notifications_user_created
    ON public.notifications(user_id, created_at);
