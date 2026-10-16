module "data" {
  source = "../../modules/data"
}

module "ingest" {
  source = "../../modules/ingest"

  zip_path       = "${path.root}/../../../dist/pipeline.zip"
  table_name     = module.data.table_name
  table_arn      = module.data.table_arn
  household_ids  = var.household_ids
  nws_user_agent = var.nws_user_agent
}

module "mcp_server" {
  source = "../../modules/mcp_server"

  zip_path                = "${path.root}/../../../dist/mcp_server.zip"
  provisioned_concurrency = var.provisioned_concurrency
  table_name              = module.data.table_name
  table_arn               = module.data.table_arn
  household_id            = var.household_ids[0]
}
