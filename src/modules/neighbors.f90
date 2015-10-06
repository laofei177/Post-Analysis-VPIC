!*******************************************************************************
! Module including the indices of the two adjoint points for finite difference
! method.
!*******************************************************************************
module neighbors_module
    use constants, only: fp, dp
    use picinfo, only: domain
    implicit none
    private
    public ixl, ixh, iyl, iyh, izl, izh, idx, idy, idz
    public init_neighbors, free_neighbors, get_neighbors

    ! The indices of the neighbors.
    integer, allocatable, dimension(:) :: ixl, ixh, iyl, iyh, izl, izh
    ! The inverse of the distance between the neighbors.
    real(dp), allocatable, dimension(:) :: idx, idy, idz
    ! The sizes in each dimension.
    integer :: nx, ny, nz

    contains

    !---------------------------------------------------------------------------
    ! Initialize the indices of the neighbors and the inverse of the distance
    ! between them.
    !---------------------------------------------------------------------------
    subroutine init_neighbors(nx0, ny0, nz0)
        implicit none
        integer, intent(in) :: nx0, ny0, nz0
        nx = nx0
        ny = ny0
        nz = nz0
        allocate(ixl(nx))
        allocate(ixh(nx))
        allocate(idx(nx))
        allocate(iyl(ny))
        allocate(iyh(ny))
        allocate(idy(ny))
        allocate(izl(nz))
        allocate(izh(nz))
        allocate(idz(nz))
        ixl = 0; iyl = 0; izl = 0
        ixh = 0; iyh = 0; izh = 0
        idx = 0.0; idy = 0.0; idz = 0.0
    end subroutine init_neighbors

    !---------------------------------------------------------------------------
    ! Free the indices of the neighbors and the inverse of the distance between
    ! them.
    !---------------------------------------------------------------------------
    subroutine free_neighbors
        implicit none
        deallocate(ixl, iyl, izl)
        deallocate(ixh, iyh, izh)
        deallocate(idx, idy, idz)
    end subroutine free_neighbors

    !---------------------------------------------------------------------------
    ! Decide the indices of two neighbors.
    ! Input:
    !   ntot: total number of points in this dimension.
    !   indexc: index of current point.
    ! Output:
    !   indexl: index of the neighbor with lower index.
    !   indexh: index of the neighbor with higher index.
    !---------------------------------------------------------------------------
    subroutine neighbors(ntot, indexc, indexl, indexh)
        implicit none
        integer, intent(in) :: ntot, indexc
        integer, intent(out) :: indexl, indexh
        if (ntot == 1) then
            indexl = 1
            indexh = 1
        else if (indexc == 1) then
            indexl = 1
            indexh = 2
        else if (indexc == ntot) then
            indexl = ntot - 1
            indexh = ntot
        else
            indexl = indexc - 1
            indexh = indexc + 1
        endif
    end subroutine neighbors

    !---------------------------------------------------------------------------
    ! Get the indices of the neighbors and the inverse of the distance between
    ! them.
    !---------------------------------------------------------------------------
    subroutine get_neighbors
        implicit none
        integer :: ix, iy, iz

        do ix = 1, nx
            call neighbors(nx, ix, ixl(ix), ixh(ix))
            if ((ixh(ix) - ixl(ix)) /= 0) then
                idx(ix) = domain%idx / (ixh(ix) - ixl(ix))
            else
                idx(ix) = 0.0
            endif
        enddo

        do iy = 1, ny
            call neighbors(ny, iy, iyl(iy), iyh(iy))
            if ((iyh(iy) - iyl(iy)) /= 0) then
                idy(iy) = domain%idy / (iyh(iy) - iyl(iy))
            else
                idy(iy) = 0.0
            endif
        enddo

        do iz = 1, nz
            call neighbors(nz, iz, izl(iz), izh(iz))
            if ((izh(iz) - izl(iz)) /= 0) then
                idz(iz) = domain%idz / (izh(iz) - izl(iz))
            else
                idz(iz) = 0.0
            endif
        enddo
    end subroutine get_neighbors

end module neighbors_module
