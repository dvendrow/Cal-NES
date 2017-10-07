import pygame


class Display:
    width = 0
    height = 0
    screen = None
    
    def __init__(self, width=256, height=240):
        self.width = width
        self.height = height
        self.screen = pygame.display.set_mode((width, height))
        self.screen.fill((50, 50, 50))
        pygame.display.set_caption("Cal-NES")
        pygame.display.flip()

    def draw_tile(self, lst: list):
        pygame.draw.rect(self.screen, (255, 0, 0), (0, 0, 100, 100))
        pygame.display.flip()

if __name__ == "__main__":
    d = Display()
    while True:
        pass
