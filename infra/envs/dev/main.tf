module "mcp_server" {
  source = "../../modules/mcp_server"

  zip_path                = "${path.root}/../../../dist/mcp_server.zip"
  provisioned_concurrency = var.provisioned_concurrency
}
