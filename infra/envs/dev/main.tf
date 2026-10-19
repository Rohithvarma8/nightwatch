module "data" {
  source = "../../modules/data"
}

module "notify" {
  source = "../../modules/notify"

  zip_path         = "${path.root}/../../../dist/pipeline.zip"
  table_name       = module.data.table_name
  table_arn        = module.data.table_arn
  ntfy_topic       = var.ntfy_topic
  ses_sender_email = var.ses_sender_email
}

module "escalation" {
  source = "../../modules/escalation"

  zip_path         = "${path.root}/../../../dist/pipeline.zip"
  table_name       = module.data.table_name
  table_arn        = module.data.table_arn
  notify_topic_arn = module.notify.topic_arn
}

module "ingest" {
  source = "../../modules/ingest"

  zip_path       = "${path.root}/../../../dist/pipeline.zip"
  table_name     = module.data.table_name
  table_arn      = module.data.table_arn
  household_ids  = var.household_ids
  nws_user_agent = var.nws_user_agent

  escalation_target_arn         = module.escalation.function_arn
  escalation_scheduler_role_arn = module.escalation.scheduler_role_arn
}

module "mcp_server" {
  source = "../../modules/mcp_server"

  zip_path                = "${path.root}/../../../dist/mcp_server.zip"
  provisioned_concurrency = var.provisioned_concurrency
  table_name              = module.data.table_name
  table_arn               = module.data.table_arn
  household_id            = var.household_ids[0]
  notify_topic_arn        = module.notify.topic_arn
}

module "triage" {
  source = "../../modules/triage"

  zip_path          = "${path.root}/../../../dist/triage.zip"
  table_name        = module.data.table_name
  table_arn         = module.data.table_arn
  bus_name          = module.ingest.bus_name
  model_id          = var.triage_model_id
  fallback_model_id = var.triage_fallback_model_id
}
