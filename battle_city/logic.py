from battle_city.monsters import Player, NPC, Bullet
from battle_city.basic import Direction

from typing import List
from random import random, choice


class LogicPart(object):
    game = None  # type: battle_city.game.Game

    def __init__(self, game):
        self.game = game

    async def do_it(self):
        raise NotImplementedError('do_it')


class MoveLogicPart(LogicPart):

    async def do_it(self):
        for monster in self.game.get_monsters_chain():
            monster.move()


class SetOldPositionLogicPart(LogicPart):

    async def do_it(self):
        for monster in self.game.get_monsters_chain():
            monster.set_old_position()


class TickLogicPart(LogicPart):
    ticks: int = 0

    async def do_it(self):
        self.ticks += 1

        if self.ticks >= 300:
            self.ticks = 0
            await self.unfreeze_players()

        if self.ticks % 10 == 0:
            await self.do_it_after_ticks()

    async def unfreeze_players(self):
        for player in self.game.alive_players:
            player.unset_freeze()

    async def do_it_after_ticks(self):
        await self.unset_player_actions()
        await self.spawn_bullets()
        await self.spawn_npc()
        await self.do_sth_with_npcs()

        self.game.time_left -= 1

    async def unset_player_actions(self):
        for player in self.game.alive_players:
            player.had_action = False

    async def spawn_bullets(self):
        for tank in self.game.get_tanks_chain():
            if not tank.is_shot:
                continue
            tank.is_shot = False
            await self.spawn_bullet(tank)

    async def spawn_bullet(self, tank):
        position = tank.position
        direction = tank.direction

        size = Bullet.SIZE
        half_size = size // 2

        if direction is Direction.UP:
            x = position.centerx - half_size
            y = position.top - size
        elif direction is Direction.DOWN:
            x = position.centerx - half_size
            y = position.bottom + size
        elif direction is Direction.LEFT:
            x = position.left - size
            y = position.centery - half_size
        elif direction is Direction.RIGHT:
            x = position.right + size
            y = position.centery - half_size
        else:
            x = 0
            y = 0

        bullet = Bullet(x, y)
        bullet.set_direction(direction)
        bullet.set_parent(tank)

        data = bullet.get_serialized_data(action='spawn')
        await self.game.broadcast(data)

        self.game.bullets.append(bullet)

    async def spawn_npc(self):
        if len(self.game.npcs) >= self.game.MAX_NPC_IN_AREA:
            return
        if random() > 0.6 / (len(self.game.npcs) + 1):
            return

        spawn = choice(self.game.npc_spawns)
        npc = NPC(*spawn)
        self.game.npcs.append(npc)
        self.game.npcs_left -= 1
        npc_data = npc.get_serialized_data(action='spawn')
        await self.game.broadcast(npc_data)

    async def do_sth_with_npcs(self):
        for npc in self.game.npcs:
            is_changed = npc.do_something()
            if not is_changed:
                continue
            npc_data = npc.get_serialized_data()
            await self.game.broadcast(npc_data)


class CheckCollisionsLogicPart(LogicPart):

    async def do_it(self):
        game = self.game
        players = game.alive_players
        npcs = game.npcs
        bullets = game.bullets
        walls = game.walls

        for player, bullet in self.check_collision(players, bullets):
            await self.remove_from_group(bullet, bullets)
            if bullet.parent_type == 'player':
                bullet.parent.score += 5
                await self.freeze(player)
            else:
                player.set_game_over()
                await self.remove_from_group(player, self.game.alive_players)

        for npc, bullet in self.check_collision(npcs, bullets):
            await self.remove_from_group(bullet, bullets)
            if bullet.parent_type == 'player':
                bullet.parent.score += 200
                await self.remove_from_group(npc, npcs)

        for bullet in bullets:
            if not self.is_monster_in_area(bullet):
                await self.remove_from_group(bullet, bullets)

        for bullet, wall in self.check_collision(bullets, walls):
            is_hurted = wall.hurt(bullet.direction)

            if is_hurted:
                await self.remove_from_group(bullet, bullets)

            if wall.is_destroyed:
                await self.remove_from_group(wall, walls)
                if bullet.parent_type == 'player':
                    bullet.parent.score += 5

        self.check_tank_collisions(players)
        self.check_tank_collisions(npcs)

    async def freeze(self, player: Player):
        player.set_freeze()
        data = player.get_serialized_data(action='freeze')
        await self.game.broadcast(data)

    def is_monster_in_area(self, monster): 
        position = monster.position

        width = self.game.WIDTH
        height = self.game.HEIGHT

        return (
            position.left >= 0 and position.right <= width and
            position.top >= 0 and position.bottom <= height
        )

    def check_tank_collisions(self, monsters):
        walls = self.game.walls
        for monster in monsters:
            # small probability to infity loop - we need to cancel on 5th try
            for i in range(5):
                # check_collision is very greedy - in future we need quadtree structure
                collision_walls = monster.check_collision(walls)
                if not collision_walls:
                    break
                wall = collision_walls[0]
                self.move_monster_after_check_wall(monster, wall)

        for monster in monsters:
            if monster.position.left < 0:
                monster.position.x = 0
            elif monster.position.right > self.game.WIDTH:
                monster.position.x = self.game.WIDTH - monster.SIZE

            if monster.position.top < 0:
                monster.position.y = 0
            elif monster.position.bottom > self.game.HEIGHT:
                monster.position.y = self.game.HEIGHT - monster.SIZE

    @staticmethod
    def move_monster_after_check_wall(monster, wall):
        monster_pos = monster.position
        wall_pos = wall.position

        # we need to detect direction of move using diff
        diff_x = monster.position.x - monster.old_position.x
        diff_y = monster.position.y - monster.old_position.y

        # according to diff we can move monster to selected side of wall
        if diff_x > 0:
            monster_pos.x -= monster_pos.right - wall_pos.left
        elif diff_x < 0:
            monster_pos.x -= monster_pos.left - wall_pos.right

        if diff_y > 0:
            monster_pos.y -= monster_pos.bottom - wall_pos.top
        elif diff_y < 0:
            monster_pos.y -= monster_pos.top - wall_pos.bottom

    async def remove_from_group(self, monster, group):
        data = dict(status='data', action='remove', id=monster.id.hex)
        try:
            group.remove(monster)
        except ValueError:
            pass
        else:
            await self.game.broadcast(data)

    @staticmethod
    def check_collision(group_a, group_b):
        for monster in group_a:
            collisions = monster.check_collision(group_b)
            for collision in collisions:
                yield (monster, collision)


class GameLogic(object):
    game = None  # type: battle_city.game.Game
    parts: List[LogicPart]

    def __init__(self, game):
        self.game = game
        self.parts = [
            MoveLogicPart(game),
            TickLogicPart(game),
            CheckCollisionsLogicPart(game),
            SetOldPositionLogicPart(game),
        ]

    async def step(self):
        with await self.game.step_lock:
            for part in self.parts:
                await part.do_it()

