"""Blob Evolution - Entry point."""

from blob_evolution.game import Game


def main() -> None:
    """Launch the game."""
    game = Game()
    game.run()


if __name__ == "__main__":
    main()
