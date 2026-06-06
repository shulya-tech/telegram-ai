.PHONY: list-admins add-admin remove-admin

list-admins:
	python3 admin_cli.py list

add-admin:
	@if [ -z "$(ID)" ]; then \
		echo "Usage: make add-admin ID=<telegram_user_id>"; \
		exit 1; \
	fi
	python3 admin_cli.py add $(ID)

remove-admin:
	@if [ -z "$(ID)" ]; then \
		echo "Usage: make remove-admin ID=<telegram_user_id>"; \
		exit 1; \
	fi
	python3 admin_cli.py remove $(ID)
