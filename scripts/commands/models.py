"""models: return the local supplier model catalogs without network calls."""
from core.request import CATALOGS


def run(args):
    return CATALOGS[args.provider] if args.provider else {'providers': CATALOGS}
