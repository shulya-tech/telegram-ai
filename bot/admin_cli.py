import asyncio
import sys
import argparse
from db import add_admin, remove_admin, list_admins

async def main():
    parser = argparse.ArgumentParser(description="Admin management CLI for Telegram Bot")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # List command
    subparsers.add_parser("list", help="List all admin user IDs")

    # Add command
    parser_add = subparsers.add_parser("add", help="Add an admin user ID")
    parser_add.add_argument("user_id", type=int, help="Telegram User ID to add")

    # Remove command
    parser_remove = subparsers.add_parser("remove", help="Remove an admin user ID")
    parser_remove.add_argument("user_id", type=int, help="Telegram User ID to remove")

    args = parser.parse_args()

    if args.command == "list":
        admins = await list_admins()
        if admins:
            print("Admin User IDs:")
            for admin_id in admins:
                print(f"- {admin_id}")
        else:
            print("No admins found.")

    elif args.command == "add":
        await add_admin(args.user_id)
        print(f"User ID {args.user_id} added to admins.")

    elif args.command == "remove":
        await remove_admin(args.user_id)
        print(f"User ID {args.user_id} removed from admins.")

if __name__ == "__main__":
    asyncio.run(main())
